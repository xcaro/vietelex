# vietelex

vietelex là bộ gõ tiếng Việt kiểu Simple Telex cho macOS. Ứng dụng chạy trên menu bar, bắt phím ở tầng hệ thống và chèn ký tự Unicode tiếng Việt trực tiếp.

## Tính năng

- Gõ Telex cơ bản: `aw`, `ow`, `uw`, `aa`, `ee`, `oo`, `dd`
- Dấu thanh: `s`, `f`, `r`, `x`, `j`, `z`
- Bật/tắt nhanh bằng `Ctrl+Shift`
- Reset buffer khi click chuột vào ô nhập để tránh dính trạng thái cũ
- Có validator ngữ âm để hạn chế sửa nhầm một số từ tiếng Anh

## Chạy ứng dụng

```bash
python3 app.py
```

Lần chạy đầu, app sẽ tự cài các dependency còn thiếu như `rumps` và PyObjC.

macOS cần cấp quyền Accessibility:

```text
System Settings -> Privacy & Security -> Accessibility
```

Thêm Terminal hoặc app đã build vào danh sách và bật quyền.

## Build app

```bash
pyinstaller vietelex.spec
```

