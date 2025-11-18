# -*- coding: utf-8 -*-
import os

class Config:
    """应用配置"""
    # 密钥
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    
    # 数据库配置
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:///invoice_system.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # 上传文件配置
    UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50MB
    ALLOWED_EXTENSIONS = {'pdf', 'jpg', 'jpeg', 'png'}
    
    # 发票提取公司名称关键词（用于PDF提取）
    COMPANY_NAME_KEYWORD = '标度'
    
    @staticmethod
    def init_app(app):
        # 确保上传文件夹存在
        os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)
        os.makedirs(os.path.join(Config.UPLOAD_FOLDER, 'invoices'), exist_ok=True)
        os.makedirs(os.path.join(Config.UPLOAD_FOLDER, 'receipts'), exist_ok=True)
        os.makedirs(os.path.join(Config.UPLOAD_FOLDER, 'reports'), exist_ok=True)