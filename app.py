# -*- coding: utf-8 -*-
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_file, session
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.utils import secure_filename
from datetime import datetime, date
from sqlalchemy import or_, and_
import os
import json

from config import Config
from models import db, User, InvoiceApplication, InvoiceDetail
from readpdftxt import extract_pdf_info

app = Flask(__name__, template_folder='templates')
app.config.from_object(Config)
Config.init_app(app)

# 初始化数据库
db.init_app(app)

# 初始化登录管理
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = '请先登录'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

# ==================== 认证路由 ====================

@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        login = request.form.get('login')
        password = request.form.get('password')
        
        user = User.query.filter_by(login=login).first()
        if user and user.check_password(password):
            login_user(user)
            next_page = request.args.get('next')
            return redirect(next_page or url_for('dashboard'))
        else:
            flash('登录名或密码错误', 'error')
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        login = request.form.get('login')
        name = request.form.get('name')
        password = request.form.get('password')
        role = request.form.get('role', '普通用户')
        
        if User.query.filter_by(login=login).first():
            flash('登录名已存在', 'error')
        else:
            user = User(login=login, name=name, role=role)
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            flash('注册成功，请登录', 'success')
            return redirect(url_for('login'))
    
    return render_template('register.html')

# ==================== 主页 ====================

@app.route('/dashboard')
@login_required
def dashboard():
    # 普通用户：只看自己的申请
    if current_user.role == '普通用户':
        my_applications = InvoiceApplication.query.filter_by(user_id=current_user.id).order_by(InvoiceApplication.created_at.desc()).all()
        return render_template('dashboard.html', my_applications=my_applications, pending_applications=[])
    
    # 管理员和财务：看自己的+待处理的
    my_applications = InvoiceApplication.query.filter_by(user_id=current_user.id).order_by(InvoiceApplication.created_at.desc()).all()
    pending_applications = InvoiceApplication.query.filter(
        InvoiceApplication.user_id != current_user.id,
        InvoiceApplication.status == '已提交'
    ).order_by(InvoiceApplication.created_at.desc()).all()
    
    return render_template('dashboard.html', my_applications=my_applications, pending_applications=pending_applications)

# ==================== 申请管理 ====================

@app.route('/application/create', methods=['GET', 'POST'])
@login_required
def create_application():
    if request.method == 'POST':
        name = request.form.get('name')
        reimbursement_person = request.form.get('reimbursement_person')
        is_paid = request.form.get('is_paid') == 'on'
        remarks = request.form.get('remarks', '')
        
        # 生成申请编号：YYYYMMDDHHmm + user_id
        sn = datetime.now().strftime('%Y%m%d%H%M') + str(current_user.id)
        
        application = InvoiceApplication(
            sn=sn,
            name=name,
            reimbursement_person=reimbursement_person,
            is_paid=is_paid,
            remarks=remarks,
            user_id=current_user.id,
            status='未提交'
        )
        db.session.add(application)
        db.session.commit()
        
        flash('申请创建成功', 'success')
        return redirect(url_for('edit_application', app_id=application.id))
    
    return render_template('create_application.html')

@app.route('/application/<int:app_id>/edit')
@login_required
def edit_application(app_id):
    application = InvoiceApplication.query.get_or_404(app_id)
    
    # 权限检查
    if current_user.role == '普通用户' and application.user_id != current_user.id:
        flash('没有权限', 'error')
        return redirect(url_for('dashboard'))
    
    return render_template('edit_application.html', application=application, reimbursement_types=InvoiceDetail.REIMBURSEMENT_TYPES)

@app.route('/application/<int:app_id>/delete', methods=['POST'])
@login_required
def delete_application(app_id):
    application = InvoiceApplication.query.get_or_404(app_id)
    
    if current_user.role == '普通用户' and application.user_id != current_user.id:
        return jsonify({'success': False, 'message': '没有权限'}), 403
    
    db.session.delete(application)
    db.session.commit()
    
    return jsonify({'success': True, 'message': '删除成功'})

@app.route('/application/<int:app_id>/submit', methods=['POST'])
@login_required
def submit_application(app_id):
    application = InvoiceApplication.query.get_or_404(app_id)
    
    if current_user.role == '普通用户' and application.user_id != current_user.id:
        return jsonify({'success': False, 'message': '没有权限'}), 403
    
    application.status = '已提交'
    db.session.commit()
    
    return jsonify({'success': True, 'message': '提交成功'})

@app.route('/application/<int:app_id>/mark_paid', methods=['POST'])
@login_required
def mark_paid(app_id):
    application = InvoiceApplication.query.get_or_404(app_id)
    
    if current_user.role == '普通用户' and application.user_id != current_user.id:
        return jsonify({'success': False, 'message': '没有权限'}), 403
    
    # 获取报销日期时间
    reimbursement_date_str = request.form.get('reimbursement_date')
    if not reimbursement_date_str:
        return jsonify({'success': False, 'message': '请选择报销日期时间'}), 400
    
    try:
        # 解析日期时间（格式：2024-11-15T14:30）
        reimbursement_date = datetime.strptime(reimbursement_date_str, '%Y-%m-%dT%H:%M')
    except ValueError:
        return jsonify({'success': False, 'message': '日期时间格式错误'}), 400
    
    # 处理银行回单上传
    if 'receipt_file' not in request.files:
        return jsonify({'success': False, 'message': '请上传转账回单文件'}), 400
    
    file = request.files['receipt_file']
    if not file or file.filename == '':
        return jsonify({'success': False, 'message': '请上传转账回单文件'}), 400
    
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        filename = f"{timestamp}_{filename}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], 'receipts', filename)
        file.save(filepath)
        application.bank_receipt_url = f"/uploads/receipts/{filename}"
    else:
        return jsonify({'success': False, 'message': '不支持的文件类型'}), 400
    
    application.is_paid = True
    application.status = '已报销'
    application.reimbursement_date = reimbursement_date
    db.session.commit()
    
    return jsonify({'success': True, 'message': f'标记成功，报销日期：{reimbursement_date.strftime("%Y-%m-%d %H:%M")}'})

# ==================== 用户管理（仅管理员） ====================

@app.route('/admin/users')
@login_required
def manage_users():
    """用户管理页面"""
    if current_user.role != '管理员':
        flash('没有权限访问此页面', 'error')
        return redirect(url_for('dashboard'))
    
    users = User.query.order_by(User.created_at.desc()).all()
    return render_template('manage_users.html', users=users)

@app.route('/admin/user/<int:user_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_user(user_id):
    """编辑用户"""
    if current_user.role != '管理员':
        return jsonify({'success': False, 'message': '没有权限'}), 403
    
    user = User.query.get_or_404(user_id)
    
    if request.method == 'POST':
        data = request.get_json()
        
        # 更新登录名（检查重复）
        if 'login' in data and data['login'] != user.login:
            if User.query.filter_by(login=data['login']).first():
                return jsonify({'success': False, 'message': '登录名已存在'})
            user.login = data['login']
        
        # 更新用户姓名
        if 'name' in data:
            user.name = data['name']
        
        # 更新角色
        if 'role' in data:
            user.role = data['role']
        
        # 更新密码（如果提供）
        if 'password' in data and data['password']:
            user.set_password(data['password'])
        
        db.session.commit()
        return jsonify({'success': True, 'message': '用户信息已更新'})
    
    return render_template('edit_user.html', user=user)

@app.route('/admin/user/<int:user_id>/delete', methods=['POST'])
@login_required
def delete_user(user_id):
    """删除用户"""
    if current_user.role != '管理员':
        return jsonify({'success': False, 'message': '没有权限'}), 403
    
    user = User.query.get_or_404(user_id)
    
    # 不能删除自己
    if user.id == current_user.id:
        return jsonify({'success': False, 'message': '不能删除自己的账户'})
    
    # 检查用户是否有关联的申请
    if user.applications:
        return jsonify({'success': False, 'message': f'该用户有 {len(user.applications)} 个申请，无法删除'})
    
    db.session.delete(user)
    db.session.commit()
    
    return jsonify({'success': True, 'message': '用户已删除'})

@app.route('/admin/user/create', methods=['POST'])
@login_required
def create_user():
    """创建新用户"""
    if current_user.role != '管理员':
        return jsonify({'success': False, 'message': '没有权限'}), 403
    
    data = request.get_json()
    login = data.get('login')
    name = data.get('name')
    password = data.get('password')
    role = data.get('role', '普通用户')
    
    if not login or not password or not name:
        return jsonify({'success': False, 'message': '登录名、姓名和密码不能为空'})
    
    if User.query.filter_by(login=login).first():
        return jsonify({'success': False, 'message': '登录名已存在'})
    
    user = User(login=login, name=name, role=role)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    
    return jsonify({'success': True, 'message': '用户创建成功', 'user_id': user.id})

# 注册额外的路由
from routes import register_routes
register_routes(app)

# ==================== 数据库初始化 ====================

@app.cli.command()
def init_db():
    """初始化数据库"""
    db.create_all()
    print('数据库初始化成功')
    
    # 创建默认管理员账户
    if not User.query.filter_by(login='admin').first():
        admin = User(login='admin', name='管理员', role='管理员')
        admin.set_password('admin123')
        db.session.add(admin)
        db.session.commit()
        print('默认管理员账户已创建: admin / admin123')

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        # 创建默认管理员（如果不存在）
        if not User.query.filter_by(login='admin').first():
            admin = User(login='admin', name='管理员', role='管理员')
            admin.set_password('admin123')
            db.session.add(admin)
            db.session.commit()
            print('默认管理员账户已创建: admin / admin123')
    app.run(debug=True, host='0.0.0.0', port=5000)