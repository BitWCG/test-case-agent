# 文件上传功能需求文档

## 功能概述
用户可以上传文件到服务器，支持多种文件类型，系统对上传文件进行校验和存储。

## 详细需求

### 1. 上传流程
- 用户选择本地文件，点击上传
- 系统校验文件类型、大小、内容
- 校验通过后存储文件到服务器（或对象存储）
- 返回文件访问 URL 和文件信息

### 2. 文件类型限制
- 允许的图片类型：jpg、png、gif、webp
- 允许的文档类型：pdf、doc、docx、xls、xlsx、txt
- 允许的压缩包：zip、rar
- 白名单外的文件类型拒绝上传

### 3. 文件大小限制
- 图片：最大 10 MB
- 文档：最大 50 MB
- 压缩包：最大 100 MB
- 单个文件最小 1 KB（拒绝空文件）

### 4. 文件名校验
- 文件名长度：1-255 个字符
- 不允许包含：/、\、:、*、?、"、<、>、|
- 文件名自动处理：去除首尾空格，同名文件自动重命名（添加时间戳后缀）
- 保留原始文件名，同时生成唯一存储名（UUID）

### 5. 上传限制
- 单次上传最多 10 个文件
- 同一用户 1 小时内最多上传 100 个文件
- 同一 IP 每分钟最多 30 次上传请求
- 上传并发数：同一用户最多 3 个并发上传

### 6. 安全要求
- 文件内容校验：校验文件头魔数（Magic Number），防止伪造文件类型
- 病毒扫描：上传后自动扫描病毒（扫描失败或发现病毒时拒绝上传）
- 图片文件：自动清除 EXIF 信息（防止隐私泄露）
- 文件访问：使用带签名的临时 URL（有效期 1 小时），非公开文件不可直接访问

### 7. 异常处理
- 上传过程中网络中断：支持断点续传（分片上传）
- 文件大小超过限制：返回具体限制信息
- 存储空间不足：返回"服务暂时不可用，请稍后再试"
- 并发超限：返回"上传任务过多，请等待当前任务完成"

## 接口定义

### POST /api/v1/files/upload

**请求体（multipart/form-data）：**
```
file: binary
```

**成功响应（201）：**
```json
{
  "code": 0,
  "data": {
    "file_id": "uuid-string",
    "original_name": "report.pdf",
    "storage_name": "a1b2c3d4-report.pdf",
    "url": "https://cdn.example.com/files/a1b2c3d4-report.pdf?sign=xxx&expires=3600",
    "size": 1048576,
    "type": "application/pdf",
    "uploaded_at": "2026-07-01T12:00:00Z"
  }
}
```

**失败响应 — 文件类型不允许（415）：**
```json
{
  "code": 415,
  "message": "不支持的文件类型，允许的类型：jpg、png、gif、webp、pdf、doc、docx、xls、xlsx、txt、zip、rar"
}
```

**失败响应 — 文件过大（413）：**
```json
{
  "code": 413,
  "message": "文件大小超过限制，最大允许 50 MB"
}
```

**失败响应 — 上传频率限制（429）：**
```json
{
  "code": 429,
  "message": "上传请求过于频繁，请稍后再试",
  "retry_after": 60
}
```

### POST /api/v1/files/batch-upload

**请求体（multipart/form-data）：**
```
files: binary[]
```

**成功响应（201）：**
```json
{
  "code": 0,
  "data": {
    "total": 5,
    "success": 5,
    "failed": 0,
    "files": [
      {
        "file_id": "uuid-1",
        "original_name": "image1.jpg",
        "url": "https://cdn.example.com/files/xxx.jpg?sign=xxx&expires=3600"
      }
    ]
  }
}
```

**失败响应 — 超过单次上传数量（400）：**
```json
{
  "code": 400,
  "message": "单次最多上传 10 个文件"
}
```

### GET /api/v1/files/{file_id}

**成功响应（200）：**
```json
{
  "code": 0,
  "data": {
    "file_id": "uuid-string",
    "original_name": "report.pdf",
    "size": 1048576,
    "type": "application/pdf",
    "url": "https://cdn.example.com/files/a1b2c3d4-report.pdf?sign=xxx&expires=3600",
    "uploaded_at": "2026-07-01T12:00:00Z"
  }
}
```

**失败响应 — 文件不存在（404）：**
```json
{
  "code": 404,
  "message": "文件不存在或已删除"
}
```