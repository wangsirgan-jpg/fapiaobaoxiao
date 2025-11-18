# -*- coding: utf-8 -*-
"""
PDF生成器，用于生成报销PDF文件
第一页：按报销类型汇总的表格
后续页：每页放置2个发票PDF
"""
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from PyPDF2 import PdfReader, PdfWriter
import os
from datetime import datetime
# 安装文泉驿字体
# sudo apt-get install fonts-wqy-zenhei fonts-wqy-microhei

# 或安装Noto字体
# sudo apt-get install fonts-noto-cjk
# 注册中文字体（跨平台支持）
try:
    # Windows
    pdfmetrics.registerFont(TTFont('SimSun', 'C:/Windows/Fonts/simsun.ttc'))
    FONT_NAME = 'SimSun'
except:
    try:
        # Ubuntu/Linux - 文泉驿正黑
        pdfmetrics.registerFont(TTFont('WQY', '/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc'))
        FONT_NAME = 'WQY'
    except:
        try:
            # Ubuntu/Linux - Noto字体
            pdfmetrics.registerFont(TTFont('Noto', '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc'))
            FONT_NAME = 'Noto'
        except:
            FONT_NAME = 'Helvetica'

def generate_reimbursement_pdf(application, upload_folder):
    """
    生成报销PDF文件
    
    Args:
        application: InvoiceApplication 对象
        upload_folder: 上传文件夹路径
    
    Returns:
        str: 生成的PDF文件路径
    """
    # 生成文件名
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    pdf_filename = f"{application.name}_{timestamp}_报销单.pdf"
    pdf_path = os.path.join(upload_folder, 'reports', pdf_filename)
    
    # 创建临时文件（汇总页）
    summary_path = os.path.join(upload_folder, 'reports', f"temp_summary_{timestamp}.pdf")
    
    # 生成汇总页
    generate_summary_page(application, summary_path)
    
    # 生成发票页（每页放2个发票）
    invoice_pages_path = os.path.join(upload_folder, 'reports', f"temp_invoices_{timestamp}.pdf")
    generate_invoice_pages(application, upload_folder, invoice_pages_path)
    
    # 合并PDF
    merge_pdfs([summary_path, invoice_pages_path], pdf_path)
    
    # 删除临时文件
    try:
        if os.path.exists(summary_path):
            os.remove(summary_path)
        if os.path.exists(invoice_pages_path):
            os.remove(invoice_pages_path)
    except:
        pass
    
    return pdf_path

def generate_summary_page(application, output_path):
    """生成汇总页"""
    doc = SimpleDocTemplate(output_path, pagesize=A4)
    story = []
    
    # 样式
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=18,
        textColor=colors.HexColor('#333333'),
        spaceAfter=30,
        alignment=TA_CENTER,
        fontName=FONT_NAME
    )
    
    normal_style = ParagraphStyle(
        'CustomNormal',
        parent=styles['Normal'],
        fontSize=10,
        fontName=FONT_NAME
    )
    
    # 标题
    title = Paragraph(f"{application.name} - 报销报表", title_style)
    story.append(title)
    
    # 申请编号（右对齐）
    sn_style = ParagraphStyle(
        'SNStyle',
        parent=styles['Normal'],
        fontSize=12,
        fontName=FONT_NAME,
        alignment=TA_LEFT,  # 使用 TA_LEFT，通过表格实现右对齐
        textColor=colors.HexColor('#666666'),
        spaceAfter=20
    )
    sn_text = application.sn if hasattr(application, 'sn') and application.sn else '-'
    sn_paragraph = Paragraph(f"申请编号：{sn_text}", sn_style)
    
    # 使用单行表格实现右对齐
    sn_table = Table([[sn_paragraph]], colWidths=[18*cm])
    sn_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    story.append(sn_table)
    story.append(Spacer(1, 0.3*cm))
    
    # 获取创建用户姓名
    creator_name = application.creator.name if hasattr(application, 'creator') and application.creator else '未知'
    
    # 基本信息（添加申请编号和创建人）
    info_data = [
        ['申请人：', creator_name,  '创建时间：', application.created_at.strftime('%Y-%m-%d')],
        ['发票数量：', str(application.invoice_count), '总金额：', f'￥{application.total_amount / 100:.2f}']
    ]
    
    info_table = Table(info_data, colWidths=[3*cm, 6*cm, 3*cm, 6*cm])
    info_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), FONT_NAME),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#666666')),
        ('TEXTCOLOR', (2, 0), (2, -1), colors.HexColor('#666666')),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 1*cm))
    
    # 按类型汇总
    type_summary = {}
    for detail in application.details:
        if detail.reimbursement_type:
            if detail.reimbursement_type not in type_summary:
                type_summary[detail.reimbursement_type] = {'count': 0, 'amount': 0}
            type_summary[detail.reimbursement_type]['count'] += 1
            type_summary[detail.reimbursement_type]['amount'] += detail.amount or 0
    
    # 汇总表格
    summary_title = Paragraph('报销类型汇总', ParagraphStyle(
        'SummaryTitle',
        parent=styles['Heading2'],
        fontSize=14,
        fontName=FONT_NAME,
        spaceAfter=10
    ))
    story.append(summary_title)
    
    summary_data = [['报销类型', '发票数量', '金额合计（元）']]
    for rtype, data in sorted(type_summary.items()):
        summary_data.append([
            rtype,
            str(data['count']),
            f"￥{data['amount'] / 100:.2f}"
        ])
    
    # 添加合计行
    total_count = sum(d['count'] for d in type_summary.values())
    total_amount = sum(d['amount'] for d in type_summary.values())
    summary_data.append(['合计', str(total_count), f"￥{total_amount / 100:.2f}"])
    
    summary_table = Table(summary_data, colWidths=[8*cm, 4*cm, 4*cm])
    summary_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), FONT_NAME),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4472C4')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 1, colors.grey),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#E7E6E6')),
        ('FONTNAME', (0, -1), (-1, -1), FONT_NAME),
        ('FONTSIZE', (0, -1), (-1, -1), 11),
        ('ROWBACKGROUNDS', (0, 1), (-1, -2), [colors.white, colors.HexColor('#F2F2F2')]),
    ]))
    story.append(summary_table)
    
    # 生成PDF
    doc.build(story)

def generate_invoice_pages(application, upload_folder, output_path):
    """
    生成发票页：每页放置2个发票（2行1列布局）
    - PDF文件：使用PyMuPDF转换为图片后嵌入
    - 图片文件：直接缩放嵌入
    """
    from PIL import Image
    from reportlab.pdfgen import canvas
    import io
    
    try:
        import fitz  # PyMuPDF
        pymupdf_available = True
    except ImportError:
        pymupdf_available = False
        print("警告：PyMuPDF 未安装，PDF文件将以文本信息显示")
    
    # 获取所有发票文件
    invoice_files = []
    for detail in application.details:
        if not detail.file_url:
            continue
        
        file_path = os.path.join(upload_folder, detail.file_url.lstrip('/uploads/'))
        if os.path.exists(file_path):
            invoice_files.append({
                'path': file_path,
                'detail': detail
            })
    
    if not invoice_files:
        # 如果没有发票，创建空文件
        open(output_path, 'w').close()
        return
    
    # 创建PDF
    c = canvas.Canvas(output_path, pagesize=A4)
    page_width, page_height = A4
    
    # 布局参数：2行1列
    rows = 2
    cols = 1
    margin = 1 * cm
    spacing = 0.5 * cm
    
    # 计算每个发票的区域大小
    available_width = page_width - 2 * margin - (cols - 1) * spacing
    available_height = page_height - 2 * margin - (rows - 1) * spacing
    cell_width = available_width / cols
    cell_height = available_height / rows
    
    # 逐个处理发票
    for idx, invoice_file in enumerate(invoice_files):
        # 计算位置（每2个换页）
        position = idx % 2
        if position == 0 and idx > 0:
            c.showPage()  # 新页
        
        # 计算网格位置（2行1列）
        row = position // cols
        col = position % cols
        
        # 计算坐标（从左上角开始）
        x = margin + col * (cell_width + spacing)
        y = page_height - margin - (row + 1) * cell_height - row * spacing
        
        file_path = invoice_file['path']
        file_ext = os.path.splitext(file_path)[1].lower()
        
        # 绘制边框
        c.setStrokeColor(colors.grey)
        c.setLineWidth(0.5)
        c.rect(x, y, cell_width, cell_height)
        
        img_to_draw = None
        temp_img_path = None
        
        try:
            if file_ext == '.pdf':
                # 处理PDF文件：使用PyMuPDF转换为图片
                if pymupdf_available:
                    try:
                        pdf_doc = fitz.open(file_path)
                        if len(pdf_doc) > 0:
                            # 获取第一页
                            page = pdf_doc[0]
                            # 设置缩放比例（zoom=2 相当于 144 DPI）
                            zoom = 2
                            mat = fitz.Matrix(zoom, zoom)
                            # 渲染为图片
                            pix = page.get_pixmap(matrix=mat)
                            # 保存为临时文件
                            temp_img_path = os.path.join(upload_folder, 'reports', f'temp_pdf_img_{idx}.png')
                            pix.save(temp_img_path)
                            img_to_draw = temp_img_path
                        pdf_doc.close()
                    except Exception as e:
                        print(f"PDF转图片失败 {file_path}: {e}")
                
                # 如果转换失败或PyMuPDF不可用，显示文本信息
                if not img_to_draw:
                    detail = invoice_file['detail']
                    c.setFont(FONT_NAME if FONT_NAME != 'Helvetica' else 'Helvetica', 8)
                    text_x = x + 5
                    text_y = y + cell_height - 15
                    
                    c.drawString(text_x, text_y, f"发票号: {detail.invoice_number or 'N/A'}")
                    c.drawString(text_x, text_y - 12, f"开票日期: {detail.invoice_date or 'N/A'}")
                    c.drawString(text_x, text_y - 24, f"金额: ￥{detail.amount / 100:.2f}" if detail.amount else "金额: N/A")
                    c.drawString(text_x, text_y - 36, f"类型: {detail.reimbursement_type or 'N/A'}")
                    c.drawString(text_x, text_y - 48, f"PDF文件")
                    continue
                    
            elif file_ext in ['.jpg', '.jpeg', '.png', '.bmp', '.gif']:
                # 直接使用图片文件
                img_to_draw = file_path
            
            # 如果有图片需要绘制
            if img_to_draw:
                img = Image.open(img_to_draw)
                
                # 转换为RGB
                if img.mode in ('RGBA', 'LA', 'P'):
                    background = Image.new('RGB', img.size, (255, 255, 255))
                    if img.mode == 'P':
                        img = img.convert('RGBA')
                    background.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
                    img = background
                elif img.mode != 'RGB':
                    img = img.convert('RGB')
                
                # 计算缩放比例
                img_width, img_height = img.size
                inner_margin = 5
                available_cell_width = cell_width - 2 * inner_margin
                available_cell_height = cell_height - 2 * inner_margin
                
                scale = min(available_cell_width / img_width, available_cell_height / img_height)
                new_width = img_width * scale
                new_height = img_height * scale
                
                # 居中放置
                img_x = x + (cell_width - new_width) / 2
                img_y = y + (cell_height - new_height) / 2
                
                # 绘制图片
                c.drawImage(img_to_draw, img_x, img_y, width=new_width, height=new_height, preserveAspectRatio=True)
                
                # 删除临时文件
                if temp_img_path and os.path.exists(temp_img_path):
                    try:
                        os.remove(temp_img_path)
                    except:
                        pass
                
        except Exception as e:
            # 如果处理失败，显示错误信息
            c.setFont(FONT_NAME if FONT_NAME != 'Helvetica' else 'Helvetica', 8)
            c.setFillColor(colors.red)
            c.drawString(x + 5, y + cell_height / 2, f"无法加载文件")
            c.setFillColor(colors.black)
            print(f"处理文件失败 {file_path}: {e}")
            
            # 清理临时文件
            if temp_img_path and os.path.exists(temp_img_path):
                try:
                    os.remove(temp_img_path)
                except:
                    pass
    
    c.save()

def merge_pdfs(pdf_list, output_path):
    """合并多个PDF文件"""
    pdf_writer = PdfWriter()
    
    for pdf_file in pdf_list:
        if os.path.exists(pdf_file):
            pdf_reader = PdfReader(pdf_file)
            for page in pdf_reader.pages:
                pdf_writer.add_page(page)
    
    with open(output_path, 'wb') as output_file:
        pdf_writer.write(output_file)
    output_file.close()