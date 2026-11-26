using System;
using System.Linq;
using System.IO;
using System.Text;
using System.Collections.Generic;
using Mono.Cecil;
using Mono.Cecil.Cil;

internal class PatchAssembly
{
    private class Row
    {
        public string Chinese;
        public HashSet<string> Sites;
    }
    static string Decode(string s) { return Encoding.UTF8.GetString(Convert.FromBase64String(s)); }
    static IEnumerable<TypeDefinition> Flatten(IEnumerable<TypeDefinition> roots)
    {
        foreach (var type in roots) {
            yield return type;
            foreach (var nested in Flatten(type.NestedTypes)) yield return nested;
        }
    }

    static string Operand(MethodDefinition method, object value, int added)
    {
        if(value==null)return "";
        var jump=value as Instruction;
        if(jump!=null)return "jump:"+ (method.Body.Instructions.IndexOf(jump)-added);
        var jumps=value as Instruction[];
        if(jumps!=null)return String.Join(",",jumps.Select(i=>Operand(method,i,added)));
        var member=value as MemberReference;
        if(member!=null)return member.FullName;
        return value.ToString();
    }

    static bool ReserveFloat(MethodDefinition m,Instruction i)
    {
        return m.DeclaringType.FullName=="Show_diplomacy_data_script" && m.Name=="ReserveRepaint" &&
               i.OpCode==OpCodes.Box && ((TypeReference)i.Operand).FullName=="System.Single" && i.Previous.OpCode==OpCodes.Div;
    }

    static HashSet<Instruction> TradePenalties(MethodDefinition method)
    {
        var calls = new HashSet<Instruction>();
        if (method.DeclaringType.Name != "modify_choose" || method.Name != "OnMouseDown") return calls;
        var labels = new Dictionary<int,string> {
            {749, "\nProfit from deals\n(fortnight): -"},
            {873, "\nSupport of the people\n(fortnight): -"},
            {997, "\nStandard of living\n(fortnight): -"},
            {1161, "\nLiberalization (fortnight): -"},
            {1285, "\nAgents (fortnight): -"}
        };
        var code = method.Body.Instructions;
        foreach (var item in labels) {
            var label = code.Single(i => i.Offset == item.Key);
            var concat = code.Single(i => i.Offset == item.Key + 89);
            if (label.OpCode != OpCodes.Ldstr || (string)label.Operand != item.Value ||
                concat.OpCode != OpCodes.Call ||
                ((MethodReference)concat.Operand).FullName != "System.String System.String::Concat(System.String[])" ||
                concat.Next.OpCode != OpCodes.Callvirt ||
                ((MethodReference)concat.Next.Operand).FullName != "System.Void UnityEngine.TextMesh::set_text(System.String)")
                throw new InvalidDataException("Unexpected trade display at " + label.Offset);
            calls.Add(concat);
        }
        return calls;
    }

    static Dictionary<Instruction,object> SaveDate(MethodDefinition method)
    {
        var changes = new Dictionary<Instruction,object>();
        if (method.Name != "BuildOpisText" ||
            (method.DeclaringType.Name != "Savescript" && method.DeclaringType.Name != "LoadInScript")) return changes;
        var code = method.Body.Instructions;
        int begin = code.IndexOf(code.Single(i => i.OpCode == OpCodes.Ldstr && (string)i.Operand == "\nDate: "));
        int end = code.IndexOf(code.Single(i => i.OpCode == OpCodes.Ldstr && (string)i.Operand == "\nDifficulty: "));
        var date = code.Skip(begin + 1).Take(end - begin - 1).ToArray();
        var fields = date.Where(i => i.OpCode == OpCodes.Ldloca_S).ToArray();
        var separators = date.Where(i => i.OpCode == OpCodes.Ldstr).ToArray();
        if (!fields.Select(i => ((VariableDefinition)i.Operand).Index).SequenceEqual(new[] {7, 8, 9})
            || separators.Length != 2 || separators.Any(i => (string)i.Operand != "."))
            throw new InvalidDataException("Unexpected save date display: " + method.FullName);
        // The original display reads day, month, year. The save data and the
        // Russian branch keep their original field order and serialization.
        changes[fields[0]] = fields[2].Operand;
        changes[fields[2]] = fields[0].Operand;
        foreach (var separator in separators) changes[separator] = "-";
        return changes;
    }

    static bool HasTraitFallback(MethodDefinition method)
    {
        return method.DeclaringType.Name == "CitizenManager" && method.Name == "GetTraitTranslation";
    }

    static void LocalizeTraitFallback(MethodDefinition method)
    {
        // Keep the original branch target. Use the same language selector as
        // the named traits, with the stock text in its Russian argument.
        var code = method.Body.Instructions;
        var label = code[code.Count - 2];
        var ret = code[code.Count - 1];
        if (label.OpCode != OpCodes.Ldstr || (string)label.Operand != "Отсутствует" || ret.OpCode != OpCodes.Ret)
            throw new InvalidDataException("Unexpected trait fallback: " + method.FullName);
        var translation = code.First(i => i.OpCode == OpCodes.Callvirt &&
            ((MethodReference)i.Operand).FullName == "System.String TranslateScriptDLC::GetTranslation(System.String,System.String)").Operand;
        var field = method.DeclaringType.Fields.Single(f => f.Name == "translateScript" && f.FieldType.Name == "TranslateScriptDLC");
        label.OpCode = OpCodes.Ldarg_0;
        label.Operand = null;
        ret.OpCode = OpCodes.Ldfld;
        ret.Operand = field;
        var il = method.Body.GetILProcessor();
        il.Emit(OpCodes.Ldstr, "无");
        il.Emit(OpCodes.Ldstr, "Отсутствует");
        il.Emit(OpCodes.Callvirt, (MethodReference)translation);
        il.Emit(OpCodes.Ret);
    }

    static void Audit(string source, string output, IDictionary<string,Row> map, ReaderParameters settings)
    {
        var original=AssemblyDefinition.ReadAssembly(source,settings);
        var result=AssemblyDefinition.ReadAssembly(output,settings);
        var before=Flatten(original.MainModule.Types).SelectMany(t=>t.Methods).ToArray();
        var after=Flatten(result.MainModule.Types).SelectMany(t=>t.Methods).ToArray();
        var layoutTypes=new HashSet<string>(new[]{"Utils","EndingScript","EngingDLCController","OkoshkoScript","Results_text"});
        if(before.Length!=after.Length)throw new InvalidDataException("Method count changed");
        int checkedCount=0;
        for(int i=0;i<before.Length;i++)
        {
            var old=before[i];var now=after[i];
            if(old.FullName!=now.FullName || old.HasBody!=now.HasBody)throw new InvalidDataException(old.FullName);
            if(!old.HasBody)continue;
            var saveDate = SaveDate(old);
            var trade = TradePenalties(old);
            var x=old.Body.Instructions;var y=now.Body.Instructions;
            int added=old.Name=="Text" && layoutTypes.Contains(old.DeclaringType.FullName)?4:0;
            bool traitTail=HasTraitFallback(old);
            if(y.Count!=x.Count+added+(traitTail?4:0))throw new InvalidDataException("IL size: "+old.FullName);
            if(traitTail) {
                int p=x.Count-2;
                if(y[p].OpCode!=OpCodes.Ldarg_0 || y[p+1].OpCode!=OpCodes.Ldfld ||
                   ((FieldReference)y[p+1].Operand).FullName!="TranslateScriptDLC CitizenManager::translateScript" ||
                   y[p+2].OpCode!=OpCodes.Ldstr || (string)y[p+2].Operand!="无" ||
                   y[p+3].OpCode!=OpCodes.Ldstr || (string)y[p+3].Operand!=(string)x[p].Operand ||
                   y[p+4].OpCode!=OpCodes.Callvirt ||
                   ((MethodReference)y[p+4].Operand).FullName!="System.String TranslateScriptDLC::GetTranslation(System.String,System.String)" ||
                   y[p+5].OpCode!=OpCodes.Ret) throw new InvalidDataException("Trait selector: "+old.FullName);
            }
            if(added > 0) {
                string width = old.Parameters[1].ParameterType.FullName;
                string helper = (width == "System.Int32") ? "PrepareInt" : "PrepareFloat";
                string call = "System.String Nostalgames.ZhCN.ChineseLayout::" + helper + "(System.String," + width + "&)";
                if (y[0].OpCode != OpCodes.Ldarg || y[0].Operand != now.Parameters[0] ||
                    y[1].OpCode != OpCodes.Ldarga || y[1].Operand != now.Parameters[1] ||
                    y[2].OpCode != OpCodes.Call || ((MethodReference)y[2].Operand).FullName != call ||
                    y[3].OpCode != OpCodes.Starg || y[3].Operand != now.Parameters[0])
                    throw new InvalidDataException("Layout prelude: "+old.FullName);
            }
            for(int j=0;j<x.Count;j++)
            {
                var a=x[j];var b=y[j+added];string expected=Operand(old,a.Operand,0);
                if(traitTail && j>=x.Count-2){checkedCount++;continue;}
                if(a.OpCode==OpCodes.Ldstr){
                    Row row;
                    string site=old.MetadataToken.RID.ToString()+":"+a.Offset.ToString();
                    if(map.TryGetValue((string)a.Operand,out row) && (row.Sites.Count==0 || row.Sites.Contains(site))) expected=row.Chinese;
                }
                object changed;
                if (saveDate.TryGetValue(a,out changed)) expected=Operand(old,changed,0);
                if (trade.Contains(a)) expected = "System.String Nostalgames.ZhCN.ChineseLayout::FormatTradePenalty(System.String[])";
                if(ReserveFloat(old,a) && b.OpCode==OpCodes.Call && ((MethodReference)b.Operand).FullName.Contains("ChineseLayout::FormatReserve")){checkedCount++;continue;}
                if(a.OpCode!=b.OpCode || expected!=Operand(now,b.Operand,added))
                    throw new InvalidDataException("Unexpected IL change: "+old.FullName+" / "+j);
                checkedCount++;
            }
            if(old.Body.ExceptionHandlers.Count!=now.Body.ExceptionHandlers.Count || old.Body.Variables.Count!=now.Body.Variables.Count)
                throw new InvalidDataException("Control-flow metadata: "+old.FullName);
        }
        Console.WriteLine("Checked {0} methods and {1} original IL instructions",before.Length,checkedCount);
    }

    static void Launcher(string input,string output,string helperPath)
    {
        using(var a=AssemblyDefinition.ReadAssembly(input))
        using(var h=AssemblyDefinition.ReadAssembly(helperPath))
        {
            var helper=h.MainModule.GetType("Nostalgames.ZhCN.ChineseLayout");
            var names=a.MainModule.ImportReference(helper.Methods.Single(m=>m.Name=="ChineseQualityNames"));
            var label=a.MainModule.ImportReference(helper.Methods.Single(m=>m.Name=="LauncherText"));
            int quality=0,localize=0,monitor=0;
            foreach(var t in a.MainModule.Types)foreach(var m in t.Methods)
            {
                if(!m.HasBody)continue;
                var il=m.Body.GetILProcessor();
                foreach(var i in m.Body.Instructions.ToArray())
                {
                    var mr=i.Operand as MethodReference;
                    if(m.Name=="PopulateQualityDropdown" && mr!=null && mr.FullName.Contains("QualitySettings::get_names"))
                    {il.InsertAfter(i,il.Create(OpCodes.Call,names));quality++;}
                    if(m.Name=="L" && i.OpCode==OpCodes.Ret && i.Previous.OpCode==OpCodes.Ldarg_1)
                    {il.InsertBefore(i,il.Create(OpCodes.Call,label));localize++;}
                    if(m.Name=="PopulateMonitorDropdown" && i.OpCode==OpCodes.Ldstr && (string)i.Operand=="Display ")
                    {i.Operand="显示器 ";monitor++;}
                    if(t.Name=="FpsLabel" && m.Name=="Update" && i.OpCode==OpCodes.Ldstr && (string)i.Operand=="{0} fps")i.Operand="{0} 帧/秒";
                }
            }
            if(quality==0 || localize==0 || monitor!=1)throw new InvalidDataException("Launcher strings unavailable");
            a.Write(output);
        }
    }

    public static void Main(string[] args)
    {
        if(args.Length==4 && args[0]=="launcher"){Launcher(args[1],args[2],args[3]);return;}
        var map = new Dictionary<string, Row>(StringComparer.Ordinal);
        foreach (string line in File.ReadAllLines(args[2])) {
            var fields=line.Split('\t');
            map.Add(Decode(fields[0]),new Row {Chinese=Decode(fields[1]), Sites=new HashSet<string>(fields[2].Split(new[]{','},StringSplitOptions.RemoveEmptyEntries))});
        }
        var wrapped = new HashSet<string>(new[]{"Utils","EndingScript","EngingDLCController","OkoshkoScript","Results_text"},StringComparer.Ordinal);
        var seen = new HashSet<string>();
        var resolver = new DefaultAssemblyResolver();
        resolver.AddSearchDirectory(Path.GetDirectoryName(Path.GetFullPath(args[0])));
        resolver.AddSearchDirectory(Path.GetDirectoryName(Path.GetFullPath(args[3])));
        var assembly = AssemblyDefinition.ReadAssembly(args[0],new ReaderParameters {AssemblyResolver=resolver});
        var helper = AssemblyDefinition.ReadAssembly(args[3]);
        int calls = 0;
        foreach (var type in Flatten(assembly.MainModule.Types)) foreach (var method in type.Methods) {
            if (!method.HasBody) continue;
            var saveDate = SaveDate(method);
            var trade = TradePenalties(method);
            foreach (var instruction in method.Body.Instructions) {
                if (trade.Contains(instruction)) {
                    var formatter = helper.MainModule.GetType("Nostalgames.ZhCN.ChineseLayout").Methods.Single(m=>m.Name=="FormatTradePenalty");
                    instruction.Operand = assembly.MainModule.ImportReference(formatter);
                    continue;
                }
                object dateOperand;
                if (saveDate.TryGetValue(instruction,out dateOperand)) {
                    instruction.Operand=dateOperand;
                    continue;
                }
                if(ReserveFloat(method,instruction)) {
                    instruction.OpCode=OpCodes.Call;
                    instruction.Operand=assembly.MainModule.ImportReference(helper.MainModule.GetType("Nostalgames.ZhCN.ChineseLayout").Methods.Single(m=>m.Name=="FormatReserve"));
                    continue;
                }
                if(instruction.OpCode != OpCodes.Ldstr) continue;
                string original=(string)instruction.Operand;
                Row row;
                if(!map.TryGetValue(original,out row)) continue;
                string site=method.MetadataToken.RID.ToString()+":"+instruction.Offset.ToString();
                if(row.Sites.Count>0 && !row.Sites.Contains(site))continue;
                instruction.Operand=row.Chinese; calls++; seen.Add(original);
            }
            if (HasTraitFallback(method)) LocalizeTraitFallback(method);
            if (method.Name!="Text" || !wrapped.Contains(type.FullName))continue;
            if(method.Parameters.Count<2 || method.Parameters[0].ParameterType.FullName!="System.String")throw new InvalidDataException(type.Name);
            string width = method.Parameters[1].ParameterType.FullName;
            if(width != "System.Int32" && width != "System.Single")throw new InvalidDataException(method.FullName);
            string name = width == "System.Int32" ? "PrepareInt" : "PrepareFloat";
            var prepare = assembly.MainModule.ImportReference(helper.MainModule.GetType("Nostalgames.ZhCN.ChineseLayout").Methods.Single(m=>m.Name==name));
            wrapped.Remove(type.FullName);
            var il=method.Body.GetILProcessor();
            var start=method.Body.Instructions[0];
            il.InsertBefore(start,il.Create(OpCodes.Ldarg,method.Parameters[0]));
            il.InsertBefore(start,il.Create(OpCodes.Ldarga,method.Parameters[1]));
            il.InsertBefore(start,il.Create(OpCodes.Call,prepare));
            il.InsertBefore(start,il.Create(OpCodes.Starg,method.Parameters[0]));
        }
        if(wrapped.Count>0 || seen.Count!=map.Count)throw new InvalidDataException("Missed strings or layout methods: "+(map.Count-seen.Count)+" / "+wrapped.Count);
        assembly.Write(args[1]);
        Audit(args[0],args[1],map,new ReaderParameters {AssemblyResolver=resolver});
        Console.WriteLine("{0} distinct display strings, {1} operands, 5 layout methods",seen.Count,calls);
    }
}
