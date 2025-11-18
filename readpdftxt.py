# -*- coding:utf-8 -*-

import pdfplumber
import re
import datetime

def get_huochepiao(text):
    lines = text.split("\n")
    # print("text", text)
    ret = {"开票方": "中国铁路总公司"}
    for line in lines:
        if "发票号码" in line:
            # 发票号码:25129110172000044123天津市税务局开票日期:2025年11月04日
            # 使用正则提取连续的数字
            match = re.search(r'\d{20,}', line)
            if match:
                ret["发票号码"] = match.group()
        if "开票日期" in line:
            # 发票号码:25129110172000044123天津市税务局开票日期:2025年11月04日
            # 使用正则提取日期
            date_match = re.search(r'(\d{4}年\d{1,2}月\d{1,2}日)', line)
            if date_match:
                ret["开票日期"] = datetime.datetime.strptime(date_match.group(1), "%Y年%m月%d日").strftime("%Y-%m-%d")
        if "￥" in line:
            ret["价税合计"] = int(float(line.split("￥", 1)[-1].split(" ", 1)[0].strip())*100)        
        if "购买方名称" in line:
            ret["公司名称"] = line.split("购买方名称:", 1)[-1].split("统一社", 1)[0].strip()
    return ret 
    

def extract_pdf_info(pdf_path, company_name):
    """
    提取单个PDF文件的信息
    
    Args:
        pdf_path: PDF文件路径
        company_name: 公司名称关键词
    
    Returns:
        dict: 提取到的信息字典，包含发票号码、开票日期、开票方、价税合计等
    """
    ret = {}
    try:
        with pdfplumber.open(pdf_path) as pdf:
            # 读取所有页面的文本
            for page_num, page in enumerate(pdf.pages, 1):
                text = page.extract_text()
                if not text:
                    continue
                text = text.replace("(", "（").replace(")", "）")
                text = text.replace(" ", "")
                gongsi = ""
                if company_name in text:
                    if "电子客票号" in text:
                        return get_huochepiao(text)
                        
                    lines = text.split("\n")
                    for line in lines:
                        if "公司" in line and company_name not in line:
                            gongsi = line
                        if "价税合计" in line:
                            # 提取 ¥23.40 格式的金额（两位小数）
                            amount_match = re.search(r'¥(\d+\.\d{2})', line)
                            if amount_match:
                                ret["价税合计"] = int(float(amount_match.group(1))*100)
                            else:
                                ret["价税合计"] = line
                        elif "发票号码" in line:
                            # 提取至少10位连续数字
                            invoice_match = re.search(r'(\d{10,})', line)
                            if invoice_match:
                                ret["发票号码"] = invoice_match.group(1)
                            else:
                                ret["发票号码"] = line
                        elif "开票日期" in line:
                            # 提取 YYYY年MM月DD日 格式的日期
                            date_match = re.search(r'(\d{4}年\d{1,2}月\d{1,2}日)', line)
                            if date_match:
                                ret["开票日期"] = datetime.datetime.strptime(date_match.group(1), "%Y年%m月%d日").strftime("%Y-%m-%d")
                            else:
                                ret["开票日期"] = line
                        elif company_name in line:
                            ret["公司名称"] = line
                        if "售" in line and len(ret.get("开票方") or "") < 8:
                            ret["开票方"] = line
                        if ("销" in line) and len(ret.get("开票方") or "") < 8:
                            ret["开票方"] = line
                        

                    if len(ret.get("开票方") or "") < 8 and "公司名称" in ret:
                        ret["开票方"] = gongsi

                    if "开票方" in ret:
                        ret["开票方"] = ret["开票方"].replace("：", ":").rsplit(":", 1)[-1].strip()
                    if "公司名称" in ret:
                        del ret["公司名称"]                                               
                if ret:  # 如果已经找到信息，不需要继续读取其他页面
                    break
    except Exception as e:
        print(f"读取文件出错: {pdf_path}, 错误: {e}")
    return ret


if __name__ == "__main__":        
    # 单独提取某个文件的信息
    single_file = r"D:\winuserfile\document\fapiao\21101023.pdf"
    result = extract_pdf_info(single_file, "标度")
    print(result)