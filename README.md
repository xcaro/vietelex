# vietelex

vietelex là bộ gõ tiếng Việt kiểu Simple Telex cho macOS. Ứng dụng chạy trên menu bar, bắt phím ở tầng hệ thống và chèn ký tự Unicode tiếng Việt trực tiếp.

## Tính năng

- Gõ Telex cơ bản: `aw`, `ow`, `uw`, `aa`, `ee`, `oo`, `dd`
- Dấu thanh: `s`, `f`, `r`, `x`, `j`, `z`
- Bật/tắt bằng cách nhấn rồi thả `Ctrl+Shift`; tổ hợp có phím khác sẽ không đổi mode
- Reset buffer khi click chuột (mặc định), đổi ứng dụng hoặc phiên làm việc
- Preferences có nút bật/tắt validator và reset khi click; lưu qua lần khởi động
- Hiện `VIE!` và mục Keyboard Access khi không khởi tạo được bộ bắt phím
- Có validator ngữ âm để hạn chế sửa nhầm một số từ tiếng Anh

## Chạy ứng dụng

```bash
python3 app.py
```

Lần chạy đầu, app sẽ tự cài các dependency còn thiếu như `rumps`, PyObjC Cocoa và Quartz.

macOS cần cấp quyền Accessibility:

```text
System Settings -> Privacy & Security -> Accessibility
```

Thêm Terminal hoặc app đã build vào danh sách và bật quyền.

## Build app

```bash
pyinstaller vietelex.spec
```


## Quy ước Simple Telex

- `w` đứng riêng vẫn là `w`, không gõ tắt thành `ư`.
- `z` xóa dấu thanh; phím dấu lặp lại hoàn tác dấu và chèn phím đó.
- Lặp `w` ngay sau chuyển đổi sẽ hoàn tác toàn bộ chuyển đổi vừa thực hiện:
  `uoww` → `uow`, còn `uwoww` → `ưow` (hoàn tác lần `w` gần nhất).
- Hoàn tác bằng phím lặp tạm ngừng chuyển đổi đến hết từ.
- Không đọc lại nội dung có sẵn trong ô nhập. Khi buffer bị reset, app bắt đầu
  theo dõi từ những phím mới; không sửa ngược văn bản trước đó.
- Đổi focus bằng mã của ứng dụng đích trong cùng một cửa sổ vẫn có thể không
  được phát hiện. Có thể dùng Reset Buffer khi gặp trường hợp này.

## Kiểm thử

```bash
python3 -m unittest discover -s tests -v
```

Test engine và mô phỏng event tap không phát phím vào ứng dụng đang mở.
Trước khi phát hành, kiểm tra trực tiếp trên TextEdit, trình duyệt và editor:

- Gõ nhanh `tieengs Vieetj dduowngf`; thử chữ hoa và giữ Shift.
- Gõ `aisf`, `aisz`, `aiss`, `uoww`; thử Backspace rồi sửa dấu.
- Nhấn/thả Ctrl+Shift; thử Ctrl+Shift+phím khác và Cmd+Ctrl+Shift.
- Đổi ô nhập, đổi app, chọn/xóa văn bản, nhập Unicode rồi tiếp tục gõ.
- Từ chối/cấp lại Accessibility; kiểm tra `VIE!` và Retry Keyboard Access.
- Đổi Preferences, thoát/mở lại app để kiểm tra lưu cài đặt.
