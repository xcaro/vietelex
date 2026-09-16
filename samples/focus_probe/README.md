# Focus probe — thử nghiệm độc lập

## Kiểm tra policy đã tích hợp

```sh
python3 samples/focus_probe/production.py
```

Script này dùng `FocusService`/`AXReader` của app, không cài event tap. Log thêm
`kind` và `route` (`RAW` / `LEGACY`), chỉ in khi thuộc tính thay đổi. Với vùng
`iOSContentGroup`, thử focus ô chat → quay lại vùng điều khiển; không cần probe
đã lấy mẫu vùng điều khiển trước khi mở chat.
Chỉ khi thu thập được quan hệ parent và cùng window thì lần quay lại mới có thể
trả `kind=surface`, `route=RAW`. Nếu vẫn UNKNOWN, policy giữ flow cũ; không coi
việc prototype nhìn thấy AXGroup là đủ để xác nhận bypass đã hoạt động.

Các phần bên dưới mô tả **probe chẩn đoán ban đầu**, có timeout dài hơn và tùy chọn
bật AX nâng cao. Nó không tự phản ánh policy học vùng điều khiển của production.

Đọc phần tử đang focus qua macOS Accessibility; không import `app.py`/`hook.py`,
không cài event tap, không sửa hoặc chặn phím. Không lấy nội dung `AXValue`,
`AXSelectedText`, tiêu đề cửa sổ hoặc phím đã gõ. Log chỉ gồm tên app, PID,
role/subrole, mã phần tử focus trong phiên chạy, khả năng ghi thuộc tính và lỗi API.
Mặc định chỉ đọc; cờ `--enable-accessibility` có gửi yêu cầu bật hỗ trợ AX cho app.

## Chạy

Từ thư mục gốc repo:

```sh
python3 -m pip install pyobjc-framework-Cocoa pyobjc-framework-ApplicationServices
python3 samples/focus_probe/probe.py
```

Nếu thiếu quyền, cấp Accessibility cho Terminal/ứng dụng chạy Python tại
**System Settings → Privacy & Security → Accessibility**, rồi khởi động lại
Terminal. Script không tự hiện yêu cầu cấp quyền. Dừng bằng Ctrl+C.

Script in mẫu đầu tiên, sau đó chỉ in khi thuộc tính thay đổi (app/PID, role,
khả năng ghi, lỗi hoặc phân loại). Không có heartbeat. Chỉ đổi `focus_id` giữa
hai phần tử cùng thuộc tính sẽ không tạo dòng mới. `focus=1`, `focus=2`, ... là
mã tạm trong phiên, không phải nội dung hoặc ID của trang.
Chỉ dùng `--all` khi debug cần xem mọi mẫu, kể cả các dòng trùng nhau:

```sh
python3 samples/focus_probe/probe.py --all
```

Nếu log vẫn ghi Terminal khi đã chuyển app, dừng script cũ bằng Ctrl+C rồi chạy
lại bản mới. Mặc định script chạy Cocoa run loop để cập nhật `NSWorkspace`, rồi
đọc `AXFocusedUIElement` của app đang focus. Vòng lặp không chỉ gọi `sleep()`.
`UNKNOWN` ở Terminal với `AXValue` không ghi được vẫn là kết quả dự kiến, không
phải script bị treo. Khi đổi app, trường `app`/`pid` phải đổi theo.

Nếu thấy `cannot_complete`, đó là lỗi giao tiếp AX, không phải kết luận về loại
input hay chắc chắn thiếu quyền. Log giữ tên app/PID ngay cả khi không đọc được
phần tử. Mặc định timeout mỗi call là 1 giây (bản thử trước dùng 100 ms).
Hai đường đọc có thể so sánh độc lập:

```sh
python3 samples/focus_probe/probe.py --source app --timeout 1
python3 samples/focus_probe/probe.py --source system --timeout 1
```

Chạy lần lượt, không chạy đồng thời. Nếu đường `system` trả `cannot_complete`
nhưng đường `app` đọc được, tiếp tục thử bằng `app`. Tăng `--timeout 3` nếu muốn
kiểm tra giả thuyết app phản hồi chậm; timeout dài hơn không đảm bảo khắc phục.

### Chrome trả `AXFocusedUIElement: no_value`

Sample đọc `AXRole` của app trước khi đọc focus để cho ứng dụng cơ hội khởi tạo
Accessibility cơ bản. Chromium có cơ chế khởi tạo theo nhu cầu này. Nếu vẫn
không đọc được focus, thử:

```sh
python3 samples/focus_probe/probe.py --enable-accessibility
```

Chuyển sang Chrome, click ô input, chờ khoảng 2–3 giây. Tùy chọn này gửi
`AXEnhancedUserInterface=True` trên đối tượng app, đúng một lần mỗi PID trong
phiên probe. Không gửi lặp mỗi poll vì Chromium có thời gian chờ kích hoạt.
Không dùng danh sách tên game/app; app không hỗ trợ thuộc tính sẽ trả lỗi được
ghi trong `activation`, không làm mất kết quả focus đã đọc được.

- `activation={'...': ..., 'AXEnhancedUserInterface': 'ok'}` chỉ xác nhận yêu cầu
  được chấp nhận; vẫn cần kiểm tra `role`, `state` và lỗi đọc focus sau đó.
- Lệnh này thay đổi chế độ Accessibility của app, không chỉ đọc. Trạng thái có
  thể còn bật sau khi dừng probe; probe không tự tắt để tránh ảnh hưởng client AX
  khác. Có thể khởi động lại app đích sau thử nghiệm nếu cần.
- Cờ chỉ dùng với `--source app`; không sửa engine hoặc hook của VieTelex.

Nguồn cơ chế khởi tạo và thời gian chờ:
[Chromium BrowserCrApplication](https://chromium.googlesource.com/chromium/src/+/master/chrome/browser/chrome_browser_application_mac.mm).

Ghi log trong 60 giây (tùy chọn):

```sh
python3 samples/focus_probe/probe.py --duration 60 --json > /tmp/vietelex-focus.jsonl
```

Mở `samples/focus_probe/cases.html` trong trình duyệt, giữ script chạy và thao tác
trên trang. Không cần server hay thư viện web. Thử thêm ô tìm kiếm native, TextEdit,
trình soạn thảo code và Terminal để đối chiếu giữa các ứng dụng.

## Đọc kết quả

| Trạng thái | Bằng chứng / ý nghĩa |
|---|---|
| `TEXT` | Role nhập chữ + AXValue có thể ghi; hoặc control tùy biến có cả value và text selection có thể ghi. Là ứng viên nhập chữ, chưa chứng minh Telex an toàn. |
| `NON_TEXT` | Role rõ ràng như button/link/checkbox/static text, hoặc control disabled. |
| `SECURE` | Secure text field: nên bỏ qua chuyển dấu. |
| `UNKNOWN` | Container/canvas, thiếu quyền, lỗi AX, hoặc chưa đủ bằng chứng về khả năng nhập chữ. |

Không đọc được focus **không có nghĩa là không có input**. `AXValue` không ghi
được cũng **không có nghĩa là readonly**: một editor vẫn có thể nhận bàn phím nhưng
không cho AX thay cả nội dung. Prototype cố ý giữ trường hợp này là UNKNOWN.
Readonly đôi khi được trình duyệt thể hiện là static text (NON_TEXT), đôi khi là
text field không có bằng chứng ghi (UNKNOWN). Nếu readonly trả TEXT, ghi nhận đó
là false positive cần xử lý trước khi tích hợp.

## Các ca cần thử thủ công

| Ca | Điều cần quan sát |
|---|---|
| Text/search/textarea, ô tìm kiếm native | Có nhận TEXT không? Nếu UNKNOWN, xem role và capability nào thiếu. |
| Contenteditable có/không có role, combobox | Kiểm tra browser có công bố role/capability nhập chữ không. |
| Password | SECURE; không đọc nội dung. |
| Readonly/select/button/link/văn bản tĩnh | Không được coi là TEXT chỉ vì có value hoặc có thể chọn chữ. |
| Disabled input | Click thường giữ focus ở phần tử cũ; log phải phản ánh focus thật, không phải vị trí chuột. |
| Canvas → Enter → chat → Enter/Esc → canvas | TEXT khi chat nếu AX hỗ trợ; về UNKNOWN khi canvas thiếu thông tin. |
| Mở/đóng chat bằng chuột | Cùng kết quả như Enter, không có bộ đếm Enter hoặc trạng thái chat suy đoán. |
| Click ra ngoài / Tab / Shift+Tab | Kết quả theo focus thật; click nền không nhất thiết blur input. |
| Đổi app, đóng cửa sổ đang focus | Không dùng lại TEXT của app cũ khi query thất bại. |
| Editor/Terminal/game dùng giao diện tự vẽ | Ghi nhận UNKNOWN hoặc false positive; không thêm ngoại lệ theo tên game. |

## Giới hạn của thử nghiệm

- Poll mỗi 250 ms, chỉ log khi thuộc tính hoặc kết quả chẩn đoán thay đổi.
  Đây chưa phải cơ chế quyết định cho từng phím: có thể bỏ
  lỡ chuyển focus nhanh. Kiểm tra lại phần tử cuối mỗi sample giúp loại kết quả
  đã cũ, nhưng focus vẫn có thể đổi ngay sau khi kiểm tra.
- Mỗi AX call có timeout 1 giây; một lần sample gồm nhiều call nên có thể lâu hơn
  250 ms. Không đưa các call đồng bộ này vào keyboard callback.
- Không duyệt input bất kỳ trong cây UI rồi coi là đang nhập, không suy đoán
  focus từ Enter/WASD. Mặc định không ghi thuộc tính AX; chỉ cờ thử nghiệm
  `--enable-accessibility` mới gửi yêu cầu bật enhanced Accessibility.
- Game hoặc custom editor không công bố ô chat qua AX vẫn không phân biệt được.
  Một terminal có thể dùng cùng text role khi nhập lệnh và chạy chương trình tương tác.
- Chưa chọn chính sách xử lý UNKNOWN cho bộ gõ. Cần kết quả thực tế trước khi
  quyết định; không được âm thầm coi UNKNOWN là TEXT hoặc NON_TEXT.
- Fixture chỉ giúp kiểm tra phát hiện focus. VieTelex hiện tại vẫn có thể chặn
  WASD nếu đang chạy VIE; prototype không sửa lỗi đó.

## Kiểm thử tự động

```sh
python3 -m unittest discover -s tests -p 'test_focus_probe.py' -v
```

Tests dùng fake AX để kiểm tra phân loại, lỗi, chuyển app và việc không đọc nội
dung. Không thay thế kiểm thử thật trên macOS.

API tham khảo: [Apple AXUIElementCopyAttributeValue](https://developer.apple.com/documentation/applicationservices/1462085-axuielementcopyattributevalue),
[AX roles](https://developer.apple.com/documentation/applicationservices/carbon_accessibility/roles),
[Secure text field](https://developer.apple.com/documentation/applicationservices/kaxsecuretextfieldsubrole),
[PyObjC ApplicationServices](https://pyobjc.readthedocs.io/en/latest/apinotes/ApplicationServices.html).
