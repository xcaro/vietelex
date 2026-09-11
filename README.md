# VieTelex

Bộ gõ **Simple Telex** cho macOS, chạy trên thanh menu.

## Bắt đầu

```bash
python3 app.py
```

App tự cài thư viện còn thiếu khi chạy lần đầu. Cấp quyền cho **Terminal** hoặc app đã build tại **System Settings → Privacy & Security → Accessibility**.

Nếu thanh menu hiện `VIE!`, chọn **Keyboard Access…** để xem hướng dẫn và thử lại.

## Cách dùng

Nhấn rồi thả **Ctrl+Shift** để bật/tắt: `VIE` là gõ tiếng Việt, `ENG` là gõ thường.

| Phím | Kết quả |
|---|---|
| `aa`, `ee`, `oo` | â, ê, ô |
| `aw`, `ow`, `uw`, `dd` | ă, ơ, ư, đ |
| `s`, `f`, `r`, `x`, `j` | sắc, huyền, hỏi, ngã, nặng |
| `z` | Xóa dấu thanh |

Ví dụ: `tieengs Vieetj` → **tiếng Việt**.

- `w` đứng riêng vẫn là `w`.
- Lặp phím dấu để hoàn tác: `ass` → `as`, `aww` → `aw`. App sẽ gõ thường đến hết từ.
- **Preferences** cho phép bật/tắt kiểm tra ngữ âm và reset khi click; cài đặt được lưu tự động.
- App chỉ xử lý phần đang gõ. Nếu chuyển ô nhập rồi chữ bị sửa sai, chọn **Reset Buffer** để bắt đầu lại.

## Build và kiểm thử

Build app (cần cài PyInstaller):

```bash
pyinstaller vietelex.spec
```

Chạy test:

```bash
python3 -m unittest discover -s tests -v
```
