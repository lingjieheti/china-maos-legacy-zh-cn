"""Typeset the English-slot tutorial plates in the player's own Steam texture stream."""
from functools import lru_cache
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont
from UnityPy.export.Texture2DConverter import image_to_texture2d

# TutorialScript.eng_s in display order. The enclosing stream is hashed before use.
OFFSETS = (17188984,34892560,44289496,23448772,21375172,42215896,27595972,0,
           6820984,32779972,5784184,12004984,28632772,14078584,43252696,
           7857784,38002960,31743172,3710584,19262584,15115384,20338372)
WIDTH, HEIGHT = 1920, 1080
ROW_BYTES = WIDTH // 4 * 8
SIZE = ROW_BYTES * (HEIGHT // 4)
PAPER = ("#e6d8c5", "#30241f")
DARK = ("#251e20", "#f3e9d2")
PLUM = ("#482234", "#fff2dc")
MUTED = ("#51464b", "#e7d9c9")


def labels(page):
    # Coordinates refer to a half-size plate, before the game scales its sprite.
    result = []
    def box(x,y,w,h,s,size=15,style=PAPER):
        result.append((x,y,w,h,s,size,style))
    def row(x,step,y,w,h,names,size=15):
        for i,s in enumerate(names): box(x+i*step,y,w,h,s,size)
    if page <= 8 or page == 10:
        for i,s in enumerate(("政策纲领","经济","科技","总览","政治","战争")):
            if page == 10 and i in (3,4): continue  # Tooltip covers both labels.
            box(68+i*142,46,112,20,s)
        for i,s in enumerate(("政体","影响力","军事","经济")):
            box(836,360+i*46,104,30,s)
        if page == 2:
            box(44,420,88,25,"苏联",18,PLUM)
            for i,s in enumerate(("外交关系","经互会","华约","支持")):
                box(6+(i%2)*82,480+(i//2)*29,76,23,s,12)
            box(340,414,315,19,"恢复外交关系",15,MUTED)
            for x,y,s in ((255,440,"1979年或之后"),(529,438,"未引发对越战争"),(255,483,"关系至少70\n亲华派力量至少20"),(529,483,"尚未恢复外交关系")):
                box(x,y,232,50 if y>470 else 38,s,14,MUTED)
        if page == 10:
            box(542,36,158,26,"情报网：+1.0",14,DARK)
            box(714,46,32,18,"",12)
    if page == 9:
        box(260,40,250,30,"五不",23)
        box(27,77,722,275,
            "华国锋同志，你已获任命，接任国务院总理。\n\n"
            "前总理周恩来以廉洁和治国才能深得人心。他也支持经济改革，\n"
            "扶持了邓小平等党内改革派。1976年1月8日，周恩来逝世，\n"
            "全国民众深切哀悼，毛泽东和中共中央对此态度冷淡。\n\n"
            "毛泽东要求实行“五不”：不戴黑纱、不送花圈、不设灵堂、\n"
            "不举行追悼活动，也不悬挂周恩来遗像。这些禁令已引起不满。\n"
            "作为新任总理，你可以决定怎样执行。",17)
    if 11 <= page <= 13:
        row(74,137,46,124,21,("世界地图","经济","科技","总览","政治","战争"))
        left = (("经济体制","国家垄断资本主义"),("政党制度","人民民主"),
                ("公民权利","打击异议"),("国家结构","单一制"),
                ("传统与宗教","反对传统主义"),("军事力量","扩军"))
        for i,(caption,value) in enumerate(left):
            box(20,149+i*63,186,20,caption,13)
            box(20,174+i*63,186,30,value,15)
        box(248,114,211,44,"中国特色社会主义",18)
        box(499,114,211,44,"社会主义威权政体",17)
        box(237,195,233,20,"党内派系",14)
        box(556,196,102,17,"选举",12)
        for i,s in enumerate(("激进左派","保守派","温和派","改革派","自由派")):
            box(300,247+i*53,111,30,s,16)
        if page == 12:
            for i,s in enumerate(("苏式计划经济","自动化计划经济","国家垄断资本主义","鸟笼经济","混合经济","最低限度监管")):
                box(757+(i%2)*90,103+i//2*32,82,24,s,11)
            for i,s in enumerate(("预算达到10","党内支持度超过60","激进左派或保守派领先","毛泽东已逝世")):
                box(752,218+i*70,183,38,s,13,DARK)
        if page == 13: box(150,146,162,27,"军力：+0.6",14,DARK)
    if 14 <= page <= 16:
        row(59,142,57,129,22,("世界地图","政策纲领","科技","总览","政治","战争"))
        for x,s in zip((96,322,547,775),("工业","农业","服务业","腐败")):
            box(x,120,155,30,s,21)
        for i,s in enumerate(("军队","国家安全部","科研","国家机关","党内津贴","宣传","农业","工业","服务业","福利","国际援助","外交使团")):
            if page==16 and i==5: continue  # Arrow obscures the original cell.
            box(117+i%3*243,204+i//3*90,120,24,s)
        for y,s in ((238,"国债损失\n预算 −0.3"),(286,"债务上限：20.1"),(333,"腐败损失\n预算 −1.9　生活水平 −0.3"),(379,"投资上限：17.9")):
            if page in (15,16): s=s.replace("20.1","19.9").replace("17.9","17.8")
            box(748,y+2,192,34,s,12)
        box(837,472,103,20,"黄金储备",13)
        if page==15: box(92,137,133,26,"近两周：+0.6",14,DARK)
    if page == 17: box(80,177,124,32,"科研点数",18)
    if page in (18,22):
        row(60,142,47,127,22,("世界地图","经济","科技","政策纲领","政治","战争" if page==18 else "总览"))
    if page == 18:
        for i,s in enumerate(("贸易","影响力","领土","局势","统一度")):
            box(64,180+i*54,123,34,s)
        box(551,468,292,58,"周恩来的遗产\n改革派和自由派受到重视",14,DARK)
    if 19 <= page <= 21:
        politicians(page,box)
    if page == 22:
        for j,(title,side1,side2) in enumerate((("柬越战争","柬埔寨","越南"),("泰国内战","共产党","保皇派"))):
            y=96+j*88
            box(335,y-1,408,18,title,15)
            box(411,y+31,121,19,side1,14)
            box(542,y+31,119,19,side2,14)
            for x in (191,773):
                for i,s in enumerate(("人道","外交","情报","军援")):
                    box(x+60*(i%2),y+3+(i//2)*28,50,19,s,13)
        box(30,307,110,27,"干预点数",13)
        box(148,298,138,45,"国际援助与影响力\n近两周：+0.6",12,DARK)
    return result


def politicians(page,box):
    for j,s in enumerate(("华国锋","毛泽东","乔冠华","吴德","陈锡联","陈云","赵紫阳","张春桥")):
        box(211,(7,33,58,88,114,139,165,190)[j],114,22,s,14)
    tiers = (
        (369,152,124,118,(("毛泽东","激进左派","强硬","多病"),("江青","激进左派","强硬","严厉"),("王洪文","激进左派","强硬","善谋"))),
        (284,152,232,118,(("张春桥","激进左派","强硬","善谋"),("汪东兴","激进左派","强硬","温和"),("李先念","温和派","强硬","节俭"),("姚文元","激进左派","强硬","傲慢"))),
        (216,152,338,118,(("叶剑英","改革派","科学家","善谋"),("纪登奎","激进左派","务实","节俭"),("陈锡联","激进左派","务实","善谋"),("吴德","激进左派","强硬","严厉"),("黄华","温和派","务实","中国通"))),
        (206,125,448,117,(("赵紫阳","自由派","温和","亲西方"),("胡耀邦","自由派","温和","偶像"),("王震","温和派","强硬","中国通"),("邓小平","改革派","务实","节俭"),("陈云","改革派","务实","节俭"),("乔冠华","温和派","强硬","亲西方")))
    )
    for x,step,y,w,people in tiers:
        for i,(name,*traits) in enumerate(people):
            box(x+i*step+2,y+1,w-2,19,name,13)
            for j,t in enumerate(traits):
                box(x+i*step+61,y+26+j*18,w-62,14,t,11)
    if page == 19: return
    for i,s in enumerate(("毛泽东（83岁）","激进左派","强硬","多病")):
        box(6,11+23*i,181,15,s,12)
    box(6,104,180,100,"职务：中央军委主席\n未被调查\n未受监视\n影响力很高",14)
    box(64,240,70,16,"尝试暗杀",11,MUTED)
    for i,s in enumerate(("派往南方","派往西部","派往首都","派往北方","任外交部长","派往东部","任总理","任军委主席","支持","撤职","展开调查","监视")):
        box(13+(i%2)*102,281+(i//2)*40,72,17,s,11,MUTED if i in (7,9,10,11) else PAPER)
    if page==20: box(330,74,82,58,"总理\n中央军委\n外交部",12,DARK)


def localize_stream(source,destination,font_path):
    stream=bytearray(source.read_bytes())
    @lru_cache(maxsize=64)
    def font(size): return ImageFont.truetype(str(font_path),size)
    for page,offset in enumerate(OFFSETS,1):
        encoded=stream[offset:offset+SIZE]
        image=Image.frombytes("RGBA",(WIDTH,HEIGHT),bytes(encoded),"bcn",1).transpose(Image.Transpose.FLIP_TOP_BOTTOM)
        # Keep the tutorial's green pointers visible over the newly typeset labels.
        mask=Image.new("L",image.size)
        arrows={2:(38,272,134,424),12:(591,78,741,166),13:(207,67,357,145),
                15:(233,84,365,158),16:(596,264,738,350),20:(428,39,555,116),
                21:(203,204,330,283)}
        if page in arrows:
            area=tuple(2*n for n in arrows[page])
            r,g,b,_=image.crop(area).split()
            green=ImageChops.multiply(r.point(lambda v:255 if 130<=v<=180 else 0),
                                      g.point(lambda v:255 if 158<=v<=210 else 0))
            green=ImageChops.multiply(green,b.point(lambda v:255 if 60<=v<=112 else 0))
            mask.paste(green.filter(ImageFilter.MaxFilter(5)),area[:2])
        for x,y,w,h,s,size,(background,ink) in labels(page):
            left,top,right,bottom = x*2//4*4,y*2//4*4,((x+w)*2+3)//4*4,((y+h)*2+3)//4*4
            rect=(left,top,right,bottom)
            patch=image.crop(rect)
            before=patch.copy()
            draw=ImageDraw.Draw(patch)
            draw.rectangle((0,0,patch.width-1,patch.height-1),fill=background)
            for point in range(size*2,9,-1):
                face=font(point)
                a,c,d,e=draw.multiline_textbbox((0,0),s,font=face,spacing=3,align="center")
                if d-a <= patch.width-4 and e-c <= patch.height-3: break
            else: raise ValueError("教程图中文字超出边界："+s)
            draw.multiline_text(((patch.width-a-d)//2,(patch.height-c-e)//2),s,font=face,
                                spacing=3,align="center",fill=ink)
            patch.paste(before,(0,0),mask.crop(rect))
            image.paste(patch,(left,top))
            data,fmt=image_to_texture2d(patch,10)
            stride=patch.width//4*8
            if int(fmt)!=10 or len(data)!=stride*(patch.height//4):
                raise ValueError("教程图片压缩格式不符")
            for rownum in range(patch.height//4):
                start=offset+((HEIGHT-bottom)//4+rownum)*ROW_BYTES+left//4*8
                stream[start:start+stride]=data[rownum*stride:(rownum+1)*stride]
    destination.write_bytes(stream)
