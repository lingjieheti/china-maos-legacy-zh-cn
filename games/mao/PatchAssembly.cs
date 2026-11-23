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
            var x=old.Body.Instructions;var y=now.Body.Instructions;
            int added=old.Name=="Text" && layoutTypes.Contains(old.DeclaringType.FullName)?5:0;
            if(y.Count!=x.Count+added)throw new InvalidDataException("IL size: "+old.FullName);
            if(added>0 && (y[0].OpCode!=OpCodes.Ldarg || y[1].OpCode!=OpCodes.Ldarg ||
                y[2].OpCode!=OpCodes.Conv_R4 || y[3].OpCode!=OpCodes.Call || y[4].OpCode!=OpCodes.Starg ||
                !((MethodReference)y[3].Operand).FullName.Contains("Nostalgames.ZhCN.ChineseLayout::Prepare")))
                throw new InvalidDataException("Layout prelude: "+old.FullName);
            for(int j=0;j<x.Count;j++)
            {
                var a=x[j];var b=y[j+added];string expected=Operand(old,a.Operand,0);
                if(a.OpCode==OpCodes.Ldstr){
                    Row row;
                    string site=old.MetadataToken.RID.ToString()+":"+a.Offset.ToString();
                    if(map.TryGetValue((string)a.Operand,out row) && (row.Sites.Count==0 || row.Sites.Contains(site))) expected=row.Chinese;
                }
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
        var prepare = assembly.MainModule.ImportReference(helper.MainModule.GetType("Nostalgames.ZhCN.ChineseLayout").Methods.Single(m=>m.Name=="Prepare"));
        int calls = 0;
        foreach (var type in Flatten(assembly.MainModule.Types)) foreach (var method in type.Methods) {
            if (!method.HasBody) continue;
            foreach (var instruction in method.Body.Instructions) {
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
            if (method.Name!="Text" || !wrapped.Contains(type.FullName))continue;
            if(method.Parameters.Count<2 || method.Parameters[0].ParameterType.FullName!="System.String")throw new InvalidDataException(type.Name);
            wrapped.Remove(type.FullName);
            var il=method.Body.GetILProcessor();
            var start=method.Body.Instructions[0];
            il.InsertBefore(start,il.Create(OpCodes.Ldarg,method.Parameters[0]));
            il.InsertBefore(start,il.Create(OpCodes.Ldarg,method.Parameters[1]));
            il.InsertBefore(start,il.Create(OpCodes.Conv_R4));
            il.InsertBefore(start,il.Create(OpCodes.Call,prepare));
            il.InsertBefore(start,il.Create(OpCodes.Starg,method.Parameters[0]));
        }
        if(wrapped.Count>0 || seen.Count!=map.Count)throw new InvalidDataException("Missed strings or layout methods: "+(map.Count-seen.Count)+" / "+wrapped.Count);
        assembly.Write(args[1]);
        Audit(args[0],args[1],map,new ReaderParameters {AssemblyResolver=resolver});
        Console.WriteLine("{0} distinct display strings, {1} operands, 5 layout methods",seen.Count,calls);
    }
}
