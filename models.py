# -*- coding: utf-8 -*-
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

class User(UserMixin, db.Model):
    """用户表"""
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    login = db.Column(db.String(80), unique=True, nullable=False)  # 登录名（唯一）
    name = db.Column(db.String(100), nullable=False)  # 用户姓名
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='普通用户')  # 管理员、财务、普通用户
    created_at = db.Column(db.DateTime, default=datetime.now)
    
    # 关系：用户创建的申请
    applications = db.relationship('InvoiceApplication', backref='creator', lazy=True, foreign_keys='InvoiceApplication.user_id')
    
    def set_password(self, password):
        """设置密码"""
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        """验证密码"""
        return check_password_hash(self.password_hash, password)
    
    def to_dict(self):
        return {
            'id': self.id,
            'login': self.login,
            'name': self.name,
            'role': self.role,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None
        }


class InvoiceApplication(db.Model):
    """发票报销申请表"""
    __tablename__ = 'invoice_applications'
    
    id = db.Column(db.Integer, primary_key=True)
    sn = db.Column(db.String(50), unique=True, nullable=False)  # 申请编号（格式：YYYYMMDDHHmm+user_id）
    name = db.Column(db.String(200), nullable=False)  # 申请名称
    created_at = db.Column(db.DateTime, default=datetime.now)  # 创建时间
    total_amount = db.Column(db.Integer, default=0)  # 发票总金额（分为单位）
    invoice_count = db.Column(db.Integer, default=0)  # 发票数量
    status = db.Column(db.String(20), default='未提交')  # 未提交、已提交、已报销
    reimbursement_person = db.Column(db.String(100), nullable=False)  # 报销人
    bank_receipt_url = db.Column(db.String(500))  # 报销银行回单
    reimbursement_date = db.Column(db.DateTime)  # 报销日期时间
    is_paid = db.Column(db.Boolean, default=False)  # 是否已付款
    remarks = db.Column(db.Text)  # 备注
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)  # 创建用户ID
    
    # 关系：申请对应的发票明细
    details = db.relationship('InvoiceDetail', backref='application', lazy=True, cascade='all, delete-orphan')
    
    def update_totals(self):
        """更新发票总金额和数量"""
        self.invoice_count = len(self.details)
        self.total_amount = sum(detail.amount for detail in self.details if detail.amount)
    
    def to_dict(self):
        return {
            'id': self.id,
            'sn': self.sn,
            'name': self.name,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None,
            'total_amount': self.total_amount / 100 if self.total_amount else 0,  # 转换为元
            'total_amount_yuan': f'{self.total_amount / 100:.2f}' if self.total_amount else '0.00',
            'invoice_count': self.invoice_count,
            'status': self.status,
            'reimbursement_person': self.reimbursement_person,
            'bank_receipt_url': self.bank_receipt_url,
            'reimbursement_date': self.reimbursement_date.strftime('%Y-%m-%d %H:%M:%S') if self.reimbursement_date else None,
            'is_paid': self.is_paid,
            'remarks': self.remarks,
            'user_id': self.user_id
        }


class InvoiceDetail(db.Model):
    """发票明细表"""
    __tablename__ = 'invoice_details'
    
    id = db.Column(db.Integer, primary_key=True)
    invoice_number = db.Column(db.String(100), unique=True, nullable=False)  # 发票号码（全表唯一）
    invoice_date = db.Column(db.Date)  # 开票日期
    issuer = db.Column(db.String(200))  # 开票方
    amount = db.Column(db.Integer)  # 价税合计（分为单位）
    file_url = db.Column(db.String(500))  # 发票文件URL地址
    filename = db.Column(db.String(255))  # 原始文件名
    reimbursement_type = db.Column(db.String(50))  # 报销类型
    application_id = db.Column(db.Integer, db.ForeignKey('invoice_applications.id'), nullable=False)  # 申请表ID
    created_at = db.Column(db.DateTime, default=datetime.now)  # 创建时间
    
    # 报销类型选项
    REIMBURSEMENT_TYPES = [
        '差旅费', '会议费', '培训费', '招待费', '维修费', 
        '办公费', '交通费', '通讯费', '餐饮费', '住宿费', '其他'
    ]
    
    def to_dict(self):
        return {
            'id': self.id,
            'invoice_number': self.invoice_number,
            'invoice_date': self.invoice_date.strftime('%Y-%m-%d') if self.invoice_date else None,
            'issuer': self.issuer,
            'amount': self.amount / 100 if self.amount else 0,  # 转换为元
            'amount_yuan': f'{self.amount / 100:.2f}' if self.amount else '0.00',
            'file_url': self.file_url,
            'filename': self.filename,
            'reimbursement_type': self.reimbursement_type,
            'application_id': self.application_id,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None
        }