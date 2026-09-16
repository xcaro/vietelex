# VieTelex

Bộ gõ **Simple Telex** cho macOS, chạy trên thanh menu.

## Bắt đầu

```bash
python3 -m pip install -r requirements.txt
python3 app.py
```

App tự cài thư viện còn thiếu khi chạy lần đầu. Cấp quyền cho **Terminal** hoặc app đã build tại **System Settings → Privacy & Security → Accessibility**.

Nếu thanh menu hiện `VIE!`, chọn **Keyboard Access…** để xem hướng dẫn và thử lại.
Cửa sổ này có nút **Retry** và **Close**, không khóa các mục trên thanh menu.

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

### Nhận diện ngữ cảnh nhập

App đọc focus qua Accessibility trong worker riêng. Khi nhận diện được control
không nhập chữ hoặc ô mật khẩu, app truyền nguyên mọi phím, kể cả tổ hợp WASD,
phím giữ/lặp và modifier. Ô nhập có thể chỉnh sửa vẫn dùng Telex theo chế độ VIE.

Với vùng `iOSContentGroup`, app học vùng điều khiển từ một ô nhập là hậu duệ
của vùng đó trong cùng cửa sổ. Parent được kiểm tra role, khả năng chỉnh sửa và
window ngay khi đọc ô nhập, kể cả khi app bắt đầu theo dõi lúc chat đã mở. Quy tắc
này không dựa vào tên game hoặc phím Enter. Cần đủ dữ liệu parent/window từ AX;
một `AXGroup` bất kỳ không được tự động coi là gameplay. Bằng chứng được xóa khi
đổi ứng dụng/cửa sổ. Quan hệ này vẫn cần xác minh trực tiếp trên game đang dùng.

Nếu thiếu thư viện `ApplicationServices`, quyền AX, hoặc không đủ thông tin,
app giữ flow Telex cũ. Vì vậy ngữ cảnh chưa nhận diện được vẫn có thể gặp xung đột
phím; Terminal có thể tiếp tục gõ tiếng Việt theo flow cũ.

Để kiểm tra **đúng policy của production** mà không chặn/sửa phím:

```bash
python3 samples/focus_probe/production.py
```

Để xem quyết định routing của chính app khi tái hiện lỗi, thoát phiên VieTelex
cũ rồi chạy source với log focus (không ghi phím/nội dung):

```bash
VIETELEX_DEBUG_FOCUS=1 python3 app.py
```

Log chỉ in khi trạng thái đổi. `route=LEGACY` sau khi đóng chat cho biết flow cũ
vẫn đang được dùng; `reason` phân biệt thiếu bằng chứng, thiếu window và lỗi AX.

Quan sát `"route": "RAW"` khi đang điều khiển và `"route": "LEGACY"`,
`"kind": "text"` khi nhập. Không bật Accessibility nâng
cao của Chrome tự động. Sample chẩn đoán cũ vẫn nằm ở `samples/focus_probe/probe.py`.

Giới hạn: dữ liệu focus được cập nhật bất đồng bộ, có khoảng trễ khi chuyển ngữ
cảnh. Trong ô chat đã xác minh thuộc vùng điều khiển, Enter/Esc/Tab hoặc click
sẽ tạm truyền nguyên phím và yêu cầu lấy mẫu lại ngay. AX xác nhận vùng điều khiển
thì tiếp tục RAW; hai mẫu TEXT mới cách nhau ít nhất 80 ms thì khôi phục Telex.
Nếu không có kết quả, bảo vệ hết hạn sau 500 ms và trả về flow cũ. Vì vậy ký tự
gõ cực nhanh sau Enter trong chính ô chat có thể chưa được chuyển dấu trong khoảng
xác nhận; ô nhập thông thường không áp dụng cơ chế này. Đây không phải bật/tắt
chat dựa trên số lần nhấn Enter.

Phím đã gửi vào macOS trước khi đổi focus không thể thu hồi; cách chèn
Unicode bằng keycode A vẫn được giữ trong các ngữ cảnh Telex/fallback. Hàng đợi
được phục hồi khi có sự kiện vật lý tiếp theo nếu chờ hoàn tất quá 500 ms, nhưng
sự kiện giả đến muộn vẫn có thể ảnh hưởng trạng thái phím.

## Build và kiểm thử

Build app (cần cài PyInstaller):

```bash
pyinstaller vietelex.spec
```

Chạy test:

```bash
python3 -m unittest discover -s tests -v
```
