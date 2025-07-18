import os
import aiofiles
import logging
from app.services.ai_content_service import parse_vulnerability_xml
from app.services.ai_service import ark_ai_V3
from app.cobra.cobra import cobra
from app.services.data_validation import security_issues, type_verification, snippet_verification, get_line

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger(__name__)

def add_report(report, report1):
    for key in report:
        if key == "language":
            if not report["language"]:
                report["language"] = report1["language"]
        else:
            report[key] = report[key] + report1[key]
    return report

async def process_R1_task(user_id, file_path):
    full_path = os.path.join(f'file/{user_id}', file_path)
    try:
        cobra_list = await cobra(full_path)
    except:
        cobra_list = []
    try:
        async with aiofiles.open(full_path, 'r', encoding='utf-8') as f:
            lines = await f.readlines()
            numbered_lines = [f"{i + 1}: {line}" for i, line in enumerate(lines)]
            content = ''.join(numbered_lines)
            line_count = len(lines)
        # logger.info(f"成功读取文件 {full_path}，行数: {line_count}")
    except Exception as e:
        logger.error(f'文件打开失败process: {e}')
        return None, None, None

    chunk_size = 102400
    report = {"vulnerabilities": [],
              "dependency_count": 0,
              "issue_dependencies": 0,
              "score": 0,
              "language":''}
    l = range(0, len(content), chunk_size)
    ll = 0
    total_tokens = (0, 0)
    for i in l:
        chunk = content[i:i + chunk_size]
        prompt1 = f'''
        你是一位代码审计安全专家，你的任务是对给定的代码进行全方位的深度检查。具体包括准确判断已检出的漏洞是否确实为漏洞，以及找出所有本地规则未涵盖的漏洞。
        <本地检测漏洞>
        {cobra_list}
        </本地检测漏洞>
        以下是要检查的代码：
        <代码>
        {chunk}
        </代码>
        
        ### 漏洞分析
        对于代码中的每个漏洞，你需要完成以下操作：
        1.**缺陷类型**：准确对漏洞进行缺陷类型分类。
        2. **缺陷名称**：判断其具体缺陷名称。
        3. **确定漏洞等级**：将漏洞等级分为高危、中危、低危。
        4. **确定漏洞概率**：给出一个1到100的整数表示漏洞概率。
        5. **提供源代码行号**：指出漏洞所在的源代码行号，用[1]列表形式给出，如果多个行号，用[1,2,3]给出。
        6. **风险分析**：指出漏洞代码，并根据代码500字以上的风险分析，风险分析部分不要分条，要用几段话来表述。
        7. **修复建议**：针对该漏洞给出具体的修复建议。
        
        如果存在多个相同的漏洞在不同位置，需独立输出每个漏洞的信息。每个漏洞信息应采用以下固定格式：
        <漏洞信息>
        <缺陷类型>缺陷类型</缺陷类型>
        <缺陷名称>缺陷名称</缺陷名称>
        <漏洞等级>高危/中危/低危</漏洞等级>
        <漏洞概率>1 - 100的整数</漏洞概率>
        <源代码行号>行号</源代码行号>
        <风险分析>500字以上的风险分析内容</风险分析>
        <修复建议>具体修复建议</修复建议>
        </漏洞信息>
        
        ### 依赖项分析
        进行依赖项分析，输出依赖项个数和过时/脆弱组件个数。输出格式为：
        <依赖项分析>
        <依赖项个数>具体个数</依赖项个数>
        <过时脆弱组件个数>具体个数</过时脆弱组件个数>
        </依赖项分析>
        
        ### 安全评分
        依据代码的整体安全状况给予一个整数的安全评分，评分计算规则如下：
        - 发现≥1高危 → 评分=MAX(80 - 高危数量×5, 70)
        - 无高危但≥1中危 → 评分=MAX(90 - 中危数量×2, 80)
        - 仅低危 → 评分=MAX(100 - 低危数量×1, 90)
        <安全评分>具体分数</安全评分>
        
        ### 语言类型
        依据代码给予一个编程语言的类型，未知时提示未知。
        <语言类型>编程语言类型</语言类型>
        
        请按上述要求进行分析，严格按照格式输出，未发现漏洞则无需输出。
        '''
        try:
            response, total_token = await ark_ai_V3.get_response(prompt1, [], user_id)
            total_tokens = tuple(x + y for x, y in zip(total_token, total_tokens))
            report1 = await parse_vulnerability_xml(response)
            if not report1["vulnerabilities"]:
                ll += 1
                report = add_report(report, report1)
                continue
            else:
                snippet = []
                ty = {}
                for ii in report1["vulnerabilities"]:
                    ty[ii["defect_type"]] = ii["defect_name"]
                    snippet.append(ii['code_snippet'])
                snippet = snippet_verification(snippet)
                for index, value in enumerate(snippet):
                    if not value:
                        del report1["vulnerabilities"][index]
                    else:
                        start_line, end_line = get_line(value, line_count)
                        code_lines = ''.join(numbered_lines[start_line: end_line])
                        report1["vulnerabilities"][index]['code'] = code_lines
                        hang_value = [hang for hang in value if start_line < hang <= end_line]
                        report1["vulnerabilities"][index]['code_snippet'] = str(hang_value)
        except Exception as e:
            ll += 1
            continue


        prompt2 = f"""
        请帮我将一组分类匹配到指定的安全问题分类体系中。我提供的分类为：{ty}。
请你按照下方的security_issues字典进行匹配，务必确保匹配后的一级标题是该字典的键，且对应的二级标题是该键所对应列表中的元素，不允许出现不在该字典中的一级标题或二级标题。
security_issues字典如下：{security_issues}
如果我提供的分类中存在无法匹配的内容，请在security_issues字典如下找一个相似的，不可以出现security_issues字典没有或者二级标题不在一级标题中。
请你返回匹配后的结果，格式仍为{{一级标题:二级标题,一级标题:二级标题}}字典格式，并且顺序保持不变。
注意：只需输出字典，无需输出其他多于内容！！！！！！
        """
        try:
            response, total_token = await ark_ai_V3.get_response(prompt2, [], None)
            total_tokens = tuple(x + y for x, y in zip(total_token, total_tokens))
            report2 = eval(response)
            if len(report2) != len(ty):
                ll += 1
                # logger.warning(f"第 {i // chunk_size + 1} 个文件块解析报告为空，跳过")
                continue
            report2 = type_verification(report2)
            items = list(report2.items())
            for idx in range(len(items) - 1, -1, -1):
                key, type_value = items[idx]
                if not type_value:
                    del report1["vulnerabilities"][idx]
                else:
                    report1["vulnerabilities"][idx]["category"] = key
                    report1["vulnerabilities"][idx]["type"] = type_value
            report = add_report(report, report1)
            # logger.info(f"成功处理第 {i // chunk_size + 1} 个文件块，更新报告")
        except Exception as e:
            logger.error(e)
            ll += 1
            # logger.warning(f"第 {i // chunk_size + 1} 个文件块解析报告为空，跳过")
            continue
    return line_count, report, total_tokens