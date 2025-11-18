# -*- coding: utf-8 -*-
"""额外的路由模块，包含发票明细管理、搜索、文件操作等
这些路由需要在 app.py 中导入并注册
"""
from flask import request, jsonify, send_file, flash, redirect, url_for, render_template
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from datetime import datetime
from sqlalchemy import or_, and_, func
import os

from models import db, InvoiceApplication, InvoiceDetail
from readpdftxt import extract_pdf_info

def register_routes(app):
    """注册额外的路由"""
    
    def allowed_file(filename):
        return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']
    
    # ==================== 发票明细管理 ====================
    
    @app.route('/invoice/upload', methods=['POST'])
    @login_required
    def upload_invoice():
        """上传发票PDF文件并自动提取信息"""
        app_id = request.form.get('application_id')
        application = InvoiceApplication.query.get_or_404(app_id)
        
        # 权限检查
        if current_user.role == '普通用户' and application.user_id != current_user.id:
            return jsonify({'success': False, 'message': '没有权限'}), 403
        
        # 检查是否已付款（已付款后不能添加）
        if application.is_paid:
            return jsonify({'success': False, 'message': '已付款的申请不能添加发票'}), 400
        
        if 'file' not in request.files:
            return jsonify({'success': False, 'message': '没有文件'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'success': False, 'message': '没有选择文件'}), 400
        
        if file and allowed_file(file.filename):
            try:
                # 保存文件
                filename = file.filename.replace("..", "").replace("/", "").replace("\\", "").replace("<", "").replace(">", "")
                timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
                unique_filename = f"{timestamp}_{filename}"
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], 'invoices', unique_filename)
                file.save(filepath)
                
                # 提取PDF信息
                pdf_info = extract_pdf_info(filepath, app.config['COMPANY_NAME_KEYWORD'])
                
                if not pdf_info or '发票号码' not in pdf_info:
                    return jsonify({
                        'success': False, 
                        'message': '无法提取发票信息，请手动填写',
                        'file_url': f"/uploads/invoices/{unique_filename}",
                        'filename': filename
                    }), 200
                
                # 检查发票号码是否已存在
                existing = InvoiceDetail.query.filter_by(invoice_number=pdf_info['发票号码']).first()
                if existing:
                    # 更新现有记录的文件名和文件URL
                    existing.filename = filename
                    existing.file_url = f"/uploads/invoices/{unique_filename}"
                    db.session.commit()
                    
                    return jsonify({
                        'success': False, 
                        'message': f"发票号码 {pdf_info['发票号码']} 已存在，已更新文件",
                        'filename': filename
                    }), 400
                
                # 创建发票明细
                invoice_date = None
                if '开票日期' in pdf_info:
                    try:
                        invoice_date = datetime.strptime(pdf_info['开票日期'], '%Y-%m-%d').date()
                    except:
                        pass
                
                detail = InvoiceDetail(
                    invoice_number=pdf_info.get('发票号码', ''),
                    invoice_date=invoice_date,
                    issuer=pdf_info.get('开票方', ''),
                    amount=pdf_info.get('价税合计', 0),
                    file_url=f"/uploads/invoices/{unique_filename}",
                    filename=filename,
                    application_id=app_id
                )
                db.session.add(detail)
                
                # 更新申请表统计
                application.update_totals()
                db.session.commit()
                
                return jsonify({
                    'success': True, 
                    'message': '上传成功',
                    'filename': filename,
                    'detail': detail.to_dict()
                })
                
            except Exception as e:
                db.session.rollback()
                return jsonify({'success': False, 'message': f'上传失败: {str(e)}'}), 500
        
        return jsonify({'success': False, 'message': '不允许的文件类型'}), 400
    
    @app.route('/invoice/<int:detail_id>/update', methods=['POST'])
    @login_required
    def update_invoice(detail_id):
        """更新发票明细"""
        detail = InvoiceDetail.query.get_or_404(detail_id)
        application = detail.application
        
        # 权限检查
        if current_user.role == '普通用户' and application.user_id != current_user.id:
            return jsonify({'success': False, 'message': '没有权限'}), 403
        
        try:
            data = request.get_json()
            
            # 检查发票号码唯一性
            if 'invoice_number' in data and data['invoice_number'] != detail.invoice_number:
                existing = InvoiceDetail.query.filter_by(invoice_number=data['invoice_number']).first()
                if existing:
                    return jsonify({'success': False, 'message': '发票号码已存在'}), 400
                detail.invoice_number = data['invoice_number']
            
            if 'invoice_date' in data:
                detail.invoice_date = datetime.strptime(data['invoice_date'], '%Y-%m-%d').date()
            if 'issuer' in data:
                detail.issuer = data['issuer']
            if 'amount' in data:
                detail.amount = int(float(data['amount']) * 100)  # 转换为分
            if 'reimbursement_type' in data:
                detail.reimbursement_type = data['reimbursement_type']
            
            # 更新申请表统计
            application.update_totals()
            db.session.commit()
            
            return jsonify({'success': True, 'message': '更新成功', 'detail': detail.to_dict()})
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'message': f'更新失败: {str(e)}'}), 500
    
    @app.route('/invoice/batch_update', methods=['POST'])
    @login_required
    def batch_update_invoices():
        """批量更新发票报销类型"""
        try:
            data = request.get_json()
            invoice_ids = data.get('invoice_ids', [])
            reimbursement_type = data.get('reimbursement_type')
            
            if not invoice_ids:
                return jsonify({'success': False, 'message': '请选择至少一个发票'}), 400
            
            if not reimbursement_type:
                return jsonify({'success': False, 'message': '请选择报销类型'}), 400
            
            # 获取所有发票并检查权限
            details = InvoiceDetail.query.filter(InvoiceDetail.id.in_(invoice_ids)).all()
            
            if not details:
                return jsonify({'success': False, 'message': '未找到发票'}), 404
            
            # 检查权限（检查所有发票是否属于用户有权限的申请）
            for detail in details:
                application = detail.application
                if current_user.role == '普通用户' and application.user_id != current_user.id:
                    return jsonify({'success': False, 'message': '没有权限修改部分发票'}), 403
            
            # 批量更新
            updated_count = 0
            for detail in details:
                detail.reimbursement_type = reimbursement_type
                updated_count += 1
            
            db.session.commit()
            
            return jsonify({
                'success': True, 
                'message': f'成功更新 {updated_count} 个发票',
                'updated_count': updated_count
            })
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'message': f'批量更新失败: {str(e)}'}), 500
    
    @app.route('/invoice/<int:detail_id>/delete', methods=['POST'])
    @login_required
    def delete_invoice(detail_id):
        """删除发票明细"""
        detail = InvoiceDetail.query.get_or_404(detail_id)
        application = detail.application
        
        # 权限检查
        if current_user.role == '普通用户' and application.user_id != current_user.id:
            return jsonify({'success': False, 'message': '没有权限'}), 403
        
        try:
            # 删除文件
            if detail.file_url:
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], detail.file_url.replace('/uploads/', ''))
                if os.path.exists(file_path):
                    os.remove(file_path)
            
            db.session.delete(detail)
            
            # 更新申请表统计
            application.update_totals()
            db.session.commit()
            
            return jsonify({'success': True, 'message': '删除成功'})
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'message': f'删除失败: {str(e)}'}), 500
    
    @app.route('/invoice/manual_add', methods=['POST'])
    @login_required
    def manual_add_invoice():
        """手动添加发票明细"""
        app_id = request.form.get('application_id')
        application = InvoiceApplication.query.get_or_404(app_id)
        
        # 权限检查
        if current_user.role == '普通用户' and application.user_id != current_user.id:
            return jsonify({'success': False, 'message': '没有权限'}), 403
        
        if application.is_paid:
            return jsonify({'success': False, 'message': '已付款的申请不能添加发票'}), 400
        
        try:
            invoice_number = request.form.get('invoice_number')
            
            # 检查发票号码唯一性
            existing = InvoiceDetail.query.filter_by(invoice_number=invoice_number).first()
            if existing:
                return jsonify({'success': False, 'message': '发票号码已存在'}), 400
            
            # 处理文件上传（可选）
            file_url = None
            original_filename = None
            if 'file' in request.files:
                file = request.files['file']
                if file and file.filename != '' and allowed_file(file.filename):
                    original_filename = secure_filename(file.filename)
                    filename = secure_filename(file.filename)
                    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
                    unique_filename = f"{timestamp}_{filename}"
                    filepath = os.path.join(app.config['UPLOAD_FOLDER'], 'invoices', unique_filename)
                    file.save(filepath)
                    file_url = f"/uploads/invoices/{unique_filename}"
            
            # 创建发票明细
            invoice_date = None
            if request.form.get('invoice_date'):
                invoice_date = datetime.strptime(request.form.get('invoice_date'), '%Y-%m-%d').date()
            
            amount = 0
            if request.form.get('amount'):
                amount = int(float(request.form.get('amount')) * 100)
            
            detail = InvoiceDetail(
                invoice_number=invoice_number,
                invoice_date=invoice_date,
                issuer=request.form.get('issuer', ''),
                amount=amount,
                file_url=file_url,
                filename=original_filename,
                reimbursement_type=request.form.get('reimbursement_type'),
                application_id=app_id
            )
            db.session.add(detail)
            
            # 更新申请表统计
            application.update_totals()
            db.session.commit()
            
            return jsonify({'success': True, 'message': '添加成功', 'detail': detail.to_dict()})
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'message': f'添加失败: {str(e)}'}), 500
    
    @app.route('/application/<int:app_id>/update_info', methods=['POST'])
    @login_required
    def update_application_info(app_id):
        """更新申请基本信息（名称和报销人）"""
        application = InvoiceApplication.query.get_or_404(app_id)
        
        # 权限检查
        if current_user.role == '普通用户' and application.user_id != current_user.id:
            return jsonify({'success': False, 'message': '没有权限'}), 403
        
        try:
            data = request.get_json()
            
            if 'name' in data:
                if not data['name'] or not data['name'].strip():
                    return jsonify({'success': False, 'message': '申请名称不能为空'}), 400
                application.name = data['name'].strip()
            
            if 'reimbursement_person' in data:
                if not data['reimbursement_person'] or not data['reimbursement_person'].strip():
                    return jsonify({'success': False, 'message': '报销人不能为空'}), 400
                application.reimbursement_person = data['reimbursement_person'].strip()
            
            db.session.commit()
            
            return jsonify({
                'success': True, 
                'message': '更新成功',
                'application': application.to_dict()
            })
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'message': f'更新失败: {str(e)}'}), 500
    
    # ==================== 搜索功能 ====================
    
    @app.route('/search')
    @login_required
    def search():
        """搜索发票明细"""
        return render_template('search.html', reimbursement_types=InvoiceDetail.REIMBURSEMENT_TYPES)
    
    @app.route('/api/search', methods=['POST'])
    @login_required
    def api_search():
        """搜索API"""
        data = request.get_json()
        
        # 构建查询
        query = db.session.query(InvoiceDetail).join(InvoiceApplication)
        
        # 普通用户只能搜索自己的
        if current_user.role == '普通用户':
            query = query.filter(InvoiceApplication.user_id == current_user.id)
        
        # 应用搜索条件
        if data.get('application_name'):
            query = query.filter(InvoiceApplication.name.like(f"%{data['application_name']}%"))
        
        if data.get('reimbursement_person'):
            query = query.filter(InvoiceApplication.reimbursement_person.like(f"%{data['reimbursement_person']}%"))
        
        if data.get('is_paid') is not None:
            query = query.filter(InvoiceApplication.is_paid == data['is_paid'])
        
        if data.get('invoice_number'):
            query = query.filter(InvoiceDetail.invoice_number.like(f"%{data['invoice_number']}%"))
        
        if data.get('issuer'):
            query = query.filter(InvoiceDetail.issuer.like(f"%{data['issuer']}%"))
        
        # 日期范围
        if data.get('date_from'):
            date_from = datetime.strptime(data['date_from'], '%Y-%m-%d').date()
            query = query.filter(InvoiceDetail.invoice_date >= date_from)
        
        if data.get('date_to'):
            date_to = datetime.strptime(data['date_to'], '%Y-%m-%d').date()
            query = query.filter(InvoiceDetail.invoice_date <= date_to)
        
        # 报销类型（多选）
        if data.get('reimbursement_types'):
            query = query.filter(InvoiceDetail.reimbursement_type.in_(data['reimbursement_types']))
        
        # 执行查询
        results = query.all()
        
        # 计算汇总
        total_amount = sum(detail.amount for detail in results if detail.amount)
        
        # 按类型汇总
        type_summary = {}
        for detail in results:
            if detail.reimbursement_type:
                if detail.reimbursement_type not in type_summary:
                    type_summary[detail.reimbursement_type] = {'count': 0, 'amount': 0}
                type_summary[detail.reimbursement_type]['count'] += 1
                type_summary[detail.reimbursement_type]['amount'] += detail.amount or 0
        
        return jsonify({
            'success': True,
            'results': [detail.to_dict() for detail in results],
            'total_amount': total_amount / 100,
            'total_count': len(results),
            'type_summary': {k: {'count': v['count'], 'amount': v['amount'] / 100} for k, v in type_summary.items()}
        })
    
    # ==================== 文件操作 ====================
    
    @app.route('/uploads/<path:filename>')
    @login_required
    def uploaded_file(filename):
        """访问上传的文件"""
        return send_file(os.path.join(app.config['UPLOAD_FOLDER'], filename))
    
    @app.route('/application/<int:app_id>/generate_pdf', methods=['GET', 'POST'])
    @login_required
    def generate_pdf(app_id):
        """生成报销PDF文件"""
        application = InvoiceApplication.query.get_or_404(app_id)
        
        # 权限检查
        if current_user.role == '普通用户' and application.user_id != current_user.id:
            return jsonify({'success': False, 'message': '没有权限'}), 403
        
        try:
            from pdf_generator import generate_reimbursement_pdf
            
            # 生成PDF
            pdf_path = generate_reimbursement_pdf(application, app.config['UPLOAD_FOLDER'])
            
            return send_file(pdf_path, as_attachment=True, download_name=f"{application.name}_报销单.pdf")
        except Exception as e:
            return jsonify({'success': False, 'message': f'生成失败: {str(e)}'}), 500