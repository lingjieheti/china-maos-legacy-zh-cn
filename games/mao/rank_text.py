"""Rank possible translation row shifts using a locally supplied multilingual ONNX model."""
import argparse
from pathlib import Path
import json

from audit_text import TABLES, texts, visible


def embeddings(strings, directory):
    import numpy as np
    import onnxruntime as ort
    from tokenizers import Tokenizer
    tokenizer=Tokenizer.from_file(str(directory/"tokenizer.json"))
    tokenizer.no_padding()
    tokenizer.no_truncation()
    options=ort.SessionOptions()
    options.intra_op_num_threads=8
    options.inter_op_num_threads=1
    session=ort.InferenceSession(str(directory/"model_quantized.onnx"),options,providers=["CPUExecutionProvider"])
    encodings=tokenizer.encode_batch([s[:3500] for s in strings])
    ids=[]
    for enc in encodings:
        words=enc.ids
        ids.append(words if len(words)<=96 else words[:62]+words[-34:])
    order=sorted(range(len(ids)),key=lambda i:len(ids[i]))
    vectors=None
    for start in range(0,len(order),32):
        indices=order[start:start+32]
        maximum=max(len(ids[j]) for j in indices)
        values=np.ones((len(indices),maximum),dtype=np.int64)
        mask=np.zeros_like(values)
        for row,j in enumerate(indices):
            width=len(ids[j])
            values[row,:width]=ids[j]
            mask[row,:width]=1
        inputs={"input_ids":values,"attention_mask":mask,"token_type_ids":np.zeros_like(values)}
        result=session.run(None,{v.name:inputs[v.name] for v in session.get_inputs()})[0]
        pooled=(result*mask[:,:,None]).sum(1)/mask.sum(1)[:,None] if result.ndim==3 else result
        unit=pooled/(np.linalg.norm(pooled,axis=1,keepdims=True)+1.e-9)
        if vectors is None:vectors=np.empty((len(strings),unit.shape[1]),dtype=np.float32)
        vectors[indices]=unit
    return {s:v for s,v in zip(strings,vectors)}


def main():
    import numpy as np
    parser=argparse.ArgumentParser(description="按跨语言语义相似度排列可能错列的长句，报告仅含索引与分数")
    for name in ["original","localized","model","json"]:parser.add_argument("--"+name,type=Path,required=True)
    args=parser.parse_args()
    orig=texts(args.original)[0]
    final=texts(args.localized)[0]
    tables={}
    strings=set()
    for stem in TABLES:
        en,ru=stem+"_en",stem+"_ru"
        source=orig.get(en,"").splitlines()
        russian=orig.get(ru,"").splitlines()
        rows=[]
        for i,(s,t) in enumerate(zip(source,final[en].splitlines())):
            source_text,target_text=visible(s),visible(t)
            if not source_text or not target_text:continue
            # Focus descriptions in Russian wrap at different positions. Omit line-level RU scores there.
            rus=visible(russian[i]) if i<len(russian) and stem!="new_focuses_texts" else ""
            rows.append((i,source_text,rus,target_text))
            strings.update([source_text,rus,target_text])
        if rows:tables[en]=rows
    vectors=embeddings(sorted(strings-{""}),args.model)
    ranked=[]
    for name, rows in tables.items():
        matrix=np.asarray([vectors[r[1]] for r in rows])
        for j,(i,en,ru,t) in enumerate(rows):
            if len(en)<85:continue
            sims=matrix@vectors[t]
            best=int(np.argmax(sims))
            ranked.append({"table":name,"row":i,"en":round(float(sims[j]),4),
                           "ru":round(float(vectors[ru]@vectors[t]),4) if ru else None,
                           "nearest_en_row":rows[best][0],"lead":round(float(sims[best]-sims[j]),4)})
    ranked.sort(key=lambda r:-r["lead"])
    args.json.write_text(json.dumps(ranked,indent=2)+"\n","utf8")
    print(f"已为 {len(ranked)} 行生成核对顺序")

if __name__=="__main__":
    main()
