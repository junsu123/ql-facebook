# AI FANPAGE COMPANY — Virtual Chibi Office (V1.2)

Phần mềm quản trị marketing AI dạng **local-first**, có giao diện văn phòng 3D hoạt hình người tí hon, 9 agent (CEO + 8 nhân viên), quản lý tối đa 100 Fanpage thuộc công ty, Firefox Profile riêng cho mỗi tài khoản, bộ nhớ từng Page, tạo nội dung AI, kiểm duyệt theo quy tắc, lịch nội bộ và báo cáo KPI thủ công.

> **Phạm vi trung thực:** Đây là **bản chạy được V1 / nền tảng MVP**, chưa phải phần mềm đã kiểm định cho vận hành 100 Page thật. Không dùng Meta API, không cài extension và **không tự động nhấn Đăng trên Facebook**. Người dùng đăng bằng Firefox rồi xác nhận thủ công. Không có chức năng tự thu thập quyền Page, tài khoản hoặc Insights từ Facebook. Các API Gemini/Groq chỉ hoạt động khi bạn nhập khóa hợp lệ.

## Chạy trên Windows

1. Cài **Python 3.11+**. Firefox chưa cần cài sẵn: phần mềm có chức năng kiểm tra, tải và mở bộ cài chính thức từ Mozilla khi bạn đồng ý. Khi cài Python nhớ chọn “Add to PATH” hoặc cài Python Launcher (`py`).
2. Giải nén thư mục `ai-fanpage-company` vào ổ đĩa bất kỳ.
3. Nhấp đúp `start_windows.bat`. Lần đầu script sẽ tạo `.venv` và cài thư viện (cần Internet).
4. Trình duyệt mặc định mở `http://127.0.0.1:8765` để sử dụng phần mềm. **Chỉ chạy một instance server** trên cùng port 8765.
5. Vào **Cài đặt** và nhập Gemini hoặc Groq API key để sử dụng agent AI thực. Nếu không có key, CEO sẽ giữ yêu cầu ở trạng thái chờ, không bịa kết quả.

> Lưu ý: Firefox mở trên **máy nơi chạy backend**, không phải máy người dùng khác đang truy cập URL này. Server được cấu hình chỉ cho phép localhost.

### Cơ chế cài Firefox an toàn trên Windows

- Chỉ hỗ trợ cài tự động trên Windows 10/11 phù hợp; Windows cũ và Linux/macOS được hướng dẫn đến trang Mozilla hoặc công cụ cài đặt OS.
- Chỉ tải bản Firefox Release ổn định từ các máy chủ Mozilla qua HTTPS; không tải từ nguồn thứ ba, không yêu cầu extension.
- Bắt buộc xác minh Authenticode signer **Mozilla Corporation** và trạng thái chữ ký **Valid** trước khi mở file `.exe`.
- Mở trình cài giao diện chính thức để người dùng quyết định cài đặt và đồng ý UAC; không dùng cài đặt silent, không vượt quyền quản trị.
- Nút **Kiểm tra lại** sẽ dò đường dẫn Firefox trong Program Files, LocalAppData và Windows Registry, nên cả bản cài cho người dùng hiện tại cũng được phát hiện.
- Dữ liệu Firefox profile đang có không bị xóa hay sửa khi dùng tính năng cài Firefox.
- Nếu quá trình tải/cài bị lỗi, xem cảnh báo và dùng liên kết chính thức <https://www.firefox.com/vi/firefox/new/>.

## Chạy trên Linux/macOS (phục vụ phát triển)

```bash
./start_linux.sh
# hoặc
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8765
```

Giao diện web: `http://127.0.0.1:8765`. OpenAPI: `http://127.0.0.1:8765/api/docs`.

## Quy trình sử dụng

1. **Tài khoản Firefox** → Nếu chưa có Firefox, bấm **Tải và cài Firefox**. Phần mềm chọn bản Windows x86/x64/ARM64, tải từ Mozilla, xác minh chữ ký số Mozilla Corporation rồi mở trình cài chính thức để bạn tự chấp thuận cài đặt. Sau khi nhận diện Firefox, bấm **Thêm tài khoản**: phần mềm tạo profile độc lập và mở Firefox. Bạn đăng nhập Facebook và hoàn thành 2FA trực tiếp.
2. **Xác nhận đăng nhập**: nhấn nút sau khi đã kiểm tra thủ công. Trạng thái không có nghĩa phần mềm đã đọc/xác nhận danh tính từ Facebook.
3. **Fanpage** → Thêm Page, URL, ngành hàng, giọng văn, dữ kiện sản phẩm, gắn tài khoản Firefox. Bạn có trách nhiệm bảo đảm có quyền quản trị Page.
4. **Cài đặt AI** → chọn Gemini hoặc Groq, cung cấp key và model ID khả dụng.
5. **AI CEO** → giao nhiệm vụ; CEO thật sẽ tạo hàng đợi agent. Bấm **Tạo chiến dịch nhiều Page** để giao 1 nhiệm vụ nội dung riêng cho mỗi Page có dữ liệu. Bấm **Chạy nhiệm vụ chờ**, hoặc bật **Tự chạy nhiệm vụ AI** trong Cài đặt để worker xử lý tự động theo hạn mức/ngày. Nhiệm vụ content của Page có thể tạo bản nháp.
6. **Nội dung** → AI viết / tự tạo bản nháp → kiểm duyệt → đặt lịch. Khi đến lịch, nội dung chuyển sang `ready`, **chưa đăng Facebook**. Bật tự chạy agent sẽ phát sinh chi phí API và không tự bật theo mặc định.
7. **Mở để đăng** → Firefox mở đúng profile + Page. Sao chép bài, bạn đăng thủ công và bấm **Đã đăng** để lưu xác nhận.
8. **Báo cáo & Bộ nhớ** → nhập KPI CSV thủ công; tối thiểu 5 bản ghi để lưu bài học quan sát được cho Page.

### CSV KPI

```csv
page_id,date,views,likes,comments,shares
PYOURPAGEID,2026-11-01,1120,35,7,2
PYOURPAGEID,2026-11-02,980,27,5,1
```

`page_id` là ID **nội bộ** (hiển thị trong dữ liệu danh sách Page hoặc dùng `/api/bootstrap`), không phải Meta Page ID.

## Hạ tầng / thư mục lưu

* Windows: `%LOCALAPPDATA%\AI-Fanpage-Company\`
* Linux/macOS: `./data/` bên trong thư mục project, hoặc đặt biến môi trường `AIFC_DATA_DIR`.
* SQLite: `company.sqlite3`.
* Firefox: `profiles/FBxxxxxxxx/firefox/` — một thư mục cố định cho một tài khoản.
* Kho ảnh: `media/`.
* API keys: `api_secrets.json.enc`, mã hóa bằng Fernet với khóa riêng `local_secret.key`. Đây là cơ chế **bảo vệ cục bộ cơ bản**, không thay thế Windows DPAPI hoặc bảo vệ thư mục ở cấp hệ điều hành. Nếu kẻ tấn công đọc được cả hai tệp, họ có thể giải mã. Không đưa thư mục dữ liệu lên Git.

## Kỹ thuật

- Backend: FastAPI + SQLite (WAL), httpx, cryptography, psutil.
- Frontend: HTML/CSS/JS thuần; văn phòng hoạt hình isometric chạy trên Canvas 2D theo trạng thái nhiệm vụ. Không cần Node/npm/CDN lúc vận hành.
- Scheduler: một vòng kiểm tra trong process, 10 giây/lần; chỉ chuyển bài sang `ready` để người dùng đăng. Không chạy khi app tắt.
- AI: REST Gemini `generateContent` hoặc Groq `chat/completions`. Model có thể cấu hình, hạn mức số lần gọi/ngày. Một số model không có sẵn tùy tài khoản API.
- Agents: CEO, Research, Strategy, Content, Creative, Publishing, Customer, Analytics, Compliance. Mỗi task ghi trạng thái, kết quả, lỗi và activity log.
- Firefox: mở native bằng `--no-remote --profile <absolute_path>`. Không Selenium, không browser extension, không lấy cookie. Quản lý PID và thời điểm tiến trình để tránh đóng nhầm Firefox khác.
- Dự án chỉ phục vụ 127.0.0.1, không CORS; chưa có xác thực người dùng. **Không đưa ra Internet hoặc triển khai nhiều người dùng nếu chưa bổ sung auth, RBAC, CSRF protection, backup và secret vault chính thức.**

## Giới hạn cần hiểu trước khi đưa vào sản xuất

- Không có Meta API nên không thể đảm bảo việc tự lấy Page, xác minh đăng nhập hay phân tích dữ liệu Meta.
- Tự động hóa UI Facebook khi không được cho phép có thể trái điều khoản. Vì vậy V1 chỉ **hỗ trợ chuẩn bị và xuất bản thủ công**, không có bot thao tác Facebook, không vượt CAPTCHA/2FA, không làm giả hoạt động con người.
- Văn phòng **Canvas 2.5D isometric** với nhân vật chibi di chuyển, cử chỉ làm việc và trao đổi minh họa. Đây chưa phải engine WebGL 3D/Three.js với nhân vật rigged và camera xoay tự do. Trạng thái agent lấy từ backend, còn hoạt ảnh không phải bằng chứng trao đổi công việc thật.
- Bộ lọc nội dung chỉ kiểm tra một số quy tắc và văn bản trùng lặp. `approved` có nghĩa đã qua **quy tắc V1 nội bộ**, không bảo đảm tuân thủ pháp luật/chính sách nền tảng. Bản thảo sản phẩm sức khỏe phải do người có chuyên môn xác minh.
- Tác vụ publishing của agent tạo hướng dẫn nội bộ, không tự gửi yêu cầu xuất bản.
- Scheduler chạy khi backend đang hoạt động, không phải dịch vụ OS chạy 24/7. Nếu muốn chạy server ổn định, thiết kế thêm Windows Service.
- Để mở rộng 100 Page hoạt động thực tế: cần kiểm thử hiệu năng, lịch theo múi giờ, background worker liên tục, phân quyền nâng cao, bản sao lưu, job idempotency, xử lý media/video và đối chiếu Meta policies.

## Kiểm thử

```bash
pip install -r requirements-dev.txt
pytest -q
```

## Nguồn thông tin kỹ thuật

- Mozilla Firefox command line flags: https://firefox-source-docs.mozilla.org/browser/CommandLineParameters.html
- Gemini REST API: https://ai.google.dev/api/generate-content
- Groq REST API: https://console.groq.com/docs/api-reference
- Meta's Automated Data Collection Terms: https://www.facebook.com/legal/automated_data_collection_terms

## Cấu trúc

```text
app/              FastAPI, database, model adapter, Firefox profile manager
web/              giao diện và hình văn phòng 3D chibi
scripts/          launcher
start_windows.bat  chạy trên Windows
start_linux.sh    chạy trên Linux
requirements.txt  dependencies
```


## Văn phòng hoạt hình tương tác (V1.2)

Mở **Văn phòng 3D** để xem khu vực làm việc hoạt hình isometric của 9 nhân viên AI tí hon.
Nhân vật có chuyển động làm việc, đi lại tới khu vực trao đổi, hiển thị bong bóng trò chuyện rồi quay về vị trí.
Lưu ý quan trọng: **đây là hoạt ảnh trực quan mô phỏng**. Chỉ số nhiệm vụ, trạng thái agent và nhật ký
được lấy từ backend thật; chuyển động, cử chỉ và hội thoại dạng bong bóng không chứng minh
AI đã thực sự trao đổi lời nói.

- Nhấn nhân vật hoặc tên nhân viên bên phải để xem nhiệm vụ thực tế.
- Kéo chuột để di chuyển góc nhìn; cuộn để phóng to, nhấn đúp để đặt lại.
- Có nút tạm dừng, tăng tốc 1x/1.75x, phóng to, thu nhỏ, đặt lại.
- Đồng bộ trạng thái backend định kỳ 12 giây **không reset vị trí hoạt họa**.
- Hoàn toàn chạy offline với Canvas 2D, không tải thư viện JavaScript từ CDN.
- Tự tắt chuyển động ban đầu khi thiết bị bật `prefers-reduced-motion`.

Đây là chế độ **2.5D isometric mô phỏng 3D**, không phải engine 3D WebGL với mô hình rigged/điều khiển camera tự do.
