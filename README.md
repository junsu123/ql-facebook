# V1.11 – Kho kiến thức đã học: xem và xuất toàn bộ dữ liệu thật

- Thêm menu **📖 Kho kiến thức đã học** và nút mở nhanh từ **Học viện 10M** và **Bộ não nhân viên**.
- Hiển thị đầy đủ 5 nhóm: tóm tắt tài liệu, bài học chuyên môn từng agent, kết quả thực hành/phản biện, bộ nhớ riêng của agent và ghi chú bộ nhớ Fanpage. Chỉ hiện bản ghi đã lưu trong SQLite, không giả lập số liệu.
- Tìm kiếm nội dung, lọc theo agent, loại kiến thức và tình trạng xác minh; phân trang 25 mục, xem nguyên văn bài học hoặc tài liệu nguồn (không cắt sau 100 kết quả).
- Xuất **CSV (Excel tiếng Việt)** hoặc **JSONL** chứa tất cả bản ghi khớp bộ lọc, xử lý dạng stream để tránh tải toàn bộ vào RAM. File không chứa API key, cookie Firefox hoặc nhật ký nội bộ của model.
- Thể hiện rõ **chưa xác minh độc lập** với kết quả đào tạo MiraiAPI/Claude; nguồn gốc là tài liệu do chủ sở hữu nhập. Việc hoàn thành bài tập không đồng nghĩa kiến thức đó đã được Meta hay chuyên gia kiểm chứng.
- Chỉ đọc dữ liệu từ database trên máy nơi phần mềm chạy. ChatGPT không thể thấy bộ nhớ đã học trên máy của bạn nếu bạn chưa xuất hoặc chia sẻ dữ liệu đó.

# Bản V1.10 – Học cường độ cao qua MiraiAPI (mục tiêu 10M quota/ngày)

- Sau **Test gọi API Mirai thành công**, nếu bật **Học tập tối đa**, Học viện tự kích hoạt và bắt đầu xử lý hàng đợi tài liệu khi backend chạy.
- Mỗi tài liệu được tóm tắt theo đoạn, 9 agent có bài học chuyên môn và thêm 1–4 lượt thực hành tình huống dựa trên chính nguồn đó. Kết quả mô phỏng **không** được đánh dấu như dữ kiện Facebook đã xác minh.
- Mức mục tiêu **10.000.000 là quota quy đổi, không phải token thô**, với phép tính `(input + 5×output)×hệ số model`. Hệ số phải được chủ tài khoản kiểm chứng, quota là ước tính từ usage API.
- Mặc định chế độ tích cực chạy từng bước sau khoảng 10 giây hoặc khi kết thúc request trước đó; tôn trọng rate limit, giới hạn quota nội bộ và khoản dự trù các yêu cầu không rõ kết quả. Không tự vượt CAPTCHA, không thu thập Facebook.
- **Không thể cam kết dùng hết đúng 10M quota/ngày** nếu không đủ nguồn học có ích, API rate limit/hết quota thật hoặc backend tắt. Không tạo hội thoại rỗng chỉ để tiêu quota.
- Đặt giới hạn tiền tại nhà cung cấp MiraiAPI để tránh phát sinh chi phí ngoài dự kiến. Tài liệu chỉ được gửi lên MiraiAPI sau khi bạn xác nhận quyền sử dụng.

# AI FANPAGE COMPANY — Virtual Chibi Office (V1.11.0)

Phần mềm quản trị marketing AI dạng **local-first**, có giao diện văn phòng 3D hoạt hình người tí hon, 9 agent (CEO + 8 nhân viên), quản lý tối đa 100 Fanpage thuộc công ty, Firefox Profile riêng cho mỗi tài khoản, bộ nhớ từng Page, tạo nội dung AI, kiểm duyệt theo quy tắc, lịch nội bộ và báo cáo KPI thủ công.

> **Phạm vi trung thực:** Đây là **bản chạy được V1 / nền tảng MVP**, chưa phải phần mềm đã kiểm định cho vận hành 100 Page thật. Không dùng Meta API, không cài extension và **không tự động nhấn Đăng trên Facebook**. Người dùng đăng bằng Firefox rồi xác nhận thủ công. Không có chức năng tự thu thập quyền Page, tài khoản hoặc Insights từ Facebook. CEO dùng Claude API trực tiếp; Học viện 10M dùng MiraiAPI riêng với giới hạn quota.

## V1.10.0 – Nút Test gọi API Mirai thật từ giao diện

- Vào **Cài đặt → MiraiAPI – Học viện 10M**, nhập `MiraiAPI Key`, tên model và hệ số quota. Bấm **⚡ Test gọi API Mirai (tốn ít quota)**.
- Nút sẽ lưu riêng ba trường MiraiAPI vừa nhập, sau đó **gửi một yêu cầu suy luận ngắn** tới `POST https://api.miraiapi.com/v1/chat/completions` (khác với nút “Xem danh sách model” chỉ gọi `GET /models`).
- Phản hồi hiển thị **thành công/thất bại, model, câu trả lời, thời gian (ms), input/output tokens, quota thực hoặc quota dự trù**. Có lỗi key/model/rate limit sẽ hiển thị HTTP code phù hợp. Không trả lại/hiển thị API key từ backend.
- Dự trù quota trước khi thử (không gửi khi đã quá giới hạn nội bộ 10M). Trường hợp nhà cung cấp không trả `usage`, hệ thống giữ phần dự trù để tránh tính thiếu. **Mỗi lần nhấn có thể tiêu quota và phát sinh phí ở MiraiAPI.**
- Giới hạn câu hỏi kiểm tra và `max_tokens=64` để tiết kiệm. Test chỉ xác minh model đang cấu hình trả lời được; **không kiểm chứng chính xác số dư quota trên tài khoản MiraiAPI**.
- Không thay đổi Claude API cho CEO, Firefox profiles, dữ liệu SQLite hay phần Học viện trước đây.
- Kiểm thử backend bằng MockTransport; kiểm tra nút trong Chromium bằng mock API. **Chưa kiểm thử với API Key MiraiAPI thật**.

## V1.8.0 – Học viện 10M dùng riêng MiraiAPI (miraiapi.com)

- **Tách nhà cung cấp:** CEO và 8 agent vẫn dùng khóa Claude trực tiếp; toàn bộ yêu cầu biên soạn và đào tạo trong Học viện 10M được gửi tới **MiraiAPI**. Không làm thay đổi các nhiệm vụ CEO.
- **Kết nối chính thức:** Base URL `https://api.miraiapi.com/v1` và `POST /chat/completions` (OpenAI-compatible, `Authorization: Bearer <key>`). **Không nhầm** với dịch vụ `mirapi.ai`.
- Cài đặt có thêm **MiraiAPI Key** (mã hóa riêng), **model** và **hệ số quota của model**. Tên model phải được cấp cho key; trước khi bật học, kiểm tra trong mục `Model & giá` của `https://miraiapi.com/usage/`. Có nút lấy danh sách model từ `/v1/models` nếu provider hỗ trợ.
- **10 triệu quota quy đổi/ngày**, không phải 10 triệu token nguyên gốc: `quota = (prompt_tokens + completion_tokens * 5) * model_ratio`. Hệ số mặc định 1 là ví dụ, cần điền đúng hệ số model đang dùng. Báo cáo là **ước tính nội bộ**, quota/hạn dùng thật xem ở trang MiraiAPI.
- Giao dịch dự trù quota trước khi gửi request, khóa SQLite `BEGIN IMMEDIATE` tránh nhiều agent vượt hạn mức; ghi lại số token thực khi có usage. Khi timeout hoặc không có usage, giữ phần quota dự trù để kiểm tra lại thay vì tự gửi lại.
- Cơ chế học vẫn chỉ nạp văn bản có quyền sử dụng, tóm tắt chung rồi đào tạo 9 agent; không tự truy cập Facebook, không gọi model để cố tiêu hết hạn mức. Nguồn tài liệu đào tạo được chuyển tới nhà cung cấp MiraiAPI khi bạn bật học.
- **Chưa kiểm thử bằng MiraiAPI key thật**; chỉ có mock API. Số liệu quota nội bộ không thay thế kiểm tra hạn dùng và quota trong tài khoản MiraiAPI. Khi provider thay đổi định dạng hoặc quy tắc, cần cập nhật connector.

### Kích hoạt MiraiAPI

1. Vào `Cài đặt`, nhập **MiraiAPI Key** vào phần Học viện (không điền vào ô Claude), model được cấp quyền và **hệ số ratio** đúng theo trang `https://miraiapi.com/usage/#models`.
2. Bấm **Lưu**, chọn **Kiểm tra MiraiAPI và các model**; nếu dịch vụ không hỗ trợ liệt kê model, hãy đối chiếu tên model trong tài khoản.
3. Giới hạn quota mặc định 10.000.000/ngày, bật Học viện, nạp dữ liệu có quyền và bấm học một bước. CEO vẫn dùng khóa Claude trực tiếp như cũ.
4. Theo dõi `Học viện 10M` và trang kiểm tra quota chính thức; ngừng học nếu quota nội bộ hoặc hạn mức thực không đủ.

## V1.7.0 – Tự khởi động lại khi có code mới tải về

- **Chỉ cần kích hoạt một lần:** đóng bản cũ và khởi động với `start_windows.bat` mới. Launcher là tiến trình giám sát, không thoát sau khi mở backend.
- Khi cập nhật bằng `git pull --ff-only origin main` hoặc `update_windows.bat`, launcher đọc dấu vân tay của mã trong `app/`, `scripts/`, `web/` và `requirements.txt`; đợi thay đổi ổn định 5 giây rồi **tự restart** server. Không cần nhấn `start_windows.bat` lại.
- Nếu Claude/AI Academy/CEO có công việc đang chạy, launcher **chờ đến khi tác vụ kết thúc** trước khi restart (không tự ngắt tác vụ trả phí). Nếu tác vụ treo mãi, người dùng chủ động dừng hoặc khắc phục rồi khởi động lại.
- Nếu `requirements.txt` thay đổi, dependency được đồng bộ bằng đúng Python trong `.venv` trước khi chạy backend mới. Nếu đồng bộ thất bại, dừng cập nhật và ghi lỗi vào `%LOCALAPPDATA%\AI-Fanpage-Company\logs\startup.log`; **không tự xóa dữ liệu**.
- Trang dashboard định kỳ kiểm tra `instance_id` của backend, tự tải lại khi phiên mới lên. URL và tab đang mở được giữ nguyên.
- Thay đổi trong database, cookie, profile Firefox, log, `.venv` không kích hoạt restart. **Không tự truy cập Internet để lấy và chạy code không được người dùng chủ động cập nhật.**
- Lưu ý: tự restart chỉ có khi mở ứng dụng qua `start_windows.bat`. Nếu chạy thẳng `uvicorn`, hoặc bản V1.6 cũ còn đang chạy, phải tắt server cũ rồi khởi động bằng bản V1.7 mới.

### Cập nhật một lần nhấp

1. Đảm bảo thư mục được tạo bằng `git clone https://github.com/junsu123/ql-facebook.git` và Git for Windows được cài.
2. Trong khi ứng dụng chạy qua `start_windows.bat`, nhấp đúp `update_windows.bat` **hoặc** chạy `git pull --ff-only origin main` trong thư mục dự án.
3. Chờ hoàn thành tải code; supervisor sẽ đợi tác vụ AI xong và tự restart. Trình duyệt tự refresh. Nếu Git báo conflict/dirty tree, cập nhật dừng và không `reset --hard` để tránh mất sửa đổi cá nhân.

## V1.6.0 – CEO xây Fanpage từ tên sản phẩm + thành phần (Growth Sprint 7 ngày)

- **Chỉ cần nhập tên sản phẩm và thành phần** trong menu **Tăng trưởng 7 ngày**. Có thể chọn Fanpage sẵn có hoặc liên kết sau, chọn đối tượng mục tiêu và bổ sung số liệu nền.
- CEO tạo ngay **kế hoạch 7 ngày và 7 khung kịch bản** (hook, 3 cảnh, CTA), sau đó giao 14 nhiệm vụ cho 8 phòng ban: Research, Strategy, 7 Content, Creative, Publishing, Customer, Analytics, Compliance. Các nhiệm vụ tăng trưởng được ưu tiên trong hàng đợi AI.
- Khi đã cấu hình Claude key, CEO có thể biên soạn lại chiến lược và kịch bản bằng Claude trong một lượt gọi có giới hạn token và ngân sách. Nếu không có key hoặc hết hạn mức, bản khung vẫn được giữ lại và ghi rõ chưa được AI hoàn thiện.
- **Mục tiêu follow/tuần:** Khi không có dữ liệu lịch sử, tạo mục tiêu thử nghiệm +25 người theo dõi mới; khi có số follow mới của tuần trước, thử nghiệm tăng mục tiêu +20%; hoặc chủ sở hữu tự nhập mục tiêu. Đây là chỉ tiêu giả định, không bảo đảm kết quả.
- Nhập **tổng followers, view và tương tác thực tế mỗi ngày** để theo dõi tiến độ. Vào các ngày 3, 5 hoặc 7, nếu thấp hơn mốc tiến độ, CEO chỉ giao thêm một nhiệm vụ Analytics đánh giá lại mỗi ngày (không tạo tác vụ trùng khi sửa KPI).
- **Không có Meta API và không tự đăng bài.** Page và số liệu do người dùng liên kết/nhập thủ công; những tuyên bố về sức khỏe phải được kiểm chứng trước khi xuất bản. Không tạo follow/view giả, không đăng spam hoặc giả lập kết quả khách hàng.
- Tài liệu tham khảo chính thức từ Meta: <https://about.fb.com/news/2026/03/rewarding-original-creators-on-facebook/> và <https://www.facebook.com/business/help/397273916756139>.

## V1.5.0 – Học viện Claude cũ (đã thay bằng MiraiAPI ở V1.8)

- Menu **Học viện 10M**: nạp tài liệu văn bản có nguồn, chống trùng bằng SHA-256, cắt đoạn 4.000 ký tự và tạo bài huấn luyện riêng cho 9 agent.
- **Tóm tắt dùng chung một lần mỗi đoạn** rồi tạo bài học theo vai trò CEO/Research/Strategy/Content/Creative/Publishing/Customer/Analytics/Compliance. Bài học lưu bộ nhớ riêng theo nguồn, **chưa tự xác thực là sự thật**.
- Học viện **tắt mặc định**. Người dùng cần nhập Claude API key, chủ động bật học tự động, có tài liệu và thiết lập ngân sách trước khi chương trình thực hiện yêu cầu AI. Nếu không có dữ liệu mới, **không gọi Claude để đốt token**.
- `academy_daily_token_limit` mặc định **10.000.000 token/ngày**, áp dụng cho **tổng lời gọi Claude của cả công ty** (tính input, output, cache read, cache write và token dự trù khi call đang chạy); đây là hạn mức nội bộ **không tự đo được gói trả phí của nhà cung cấp**.
- Giữ hai lớp bảo vệ độc lập: **10M token/ngày + USD/ngày toàn công ty và từng agent**. Giới hạn `daily_llm_call_limit` còn hiệu lực: để học nhiều phải điều chỉnh phù hợp trong Cài đặt. Quota token **không đồng nghĩa được sử dụng miễn phí**.
- Worker học một bước mỗi `academy_interval_seconds` (mặc định 35 giây) khi server đang hoạt động. Có tạm dừng/bật lại; trên Windows muốn 24/24 phải để máy và server chạy. Không có crawler Facebook, không tự truy cập tài khoản người khác hoặc vượt giới hạn nền tảng.
- Nguồn học V1.5: **văn bản do chủ sở hữu cung cấp**, tối đa 300.000 ký tự/lần, có trường ghi URL/nguồn tham khảo **chỉ làm metadata, không tự tải URL**. Sau này có thể thêm bộ nhập PDF/DOCX và tài liệu từ các nguồn được phép.
- Chi phí thực tế lấy từ usage Anthropic nhưng chỉ **ước tính USD** bằng bảng giá trong mã; cần so với billing của Anthropic. Kiểm thử giả lập không tiêu API thật.

### Cách sử dụng Học viện AI

1. Vào **Cài đặt**, nhập Claude API key và xác nhận đã lưu.
2. Đặt `Hạn mức token toàn công ty/ngày` thành `10000000` (mặc định), ngân sách USD, ngân sách/agent và số lượt gọi/ngày phù hợp với hạn mức **thực tế** của bạn. Mức mặc định $1/ngày và 200 lượt/ngày sẽ làm hệ thống dừng sớm.
3. Vào **Học viện 10M** và nạp tài liệu bạn có quyền dùng. Cần ít nhất 160 ký tự/tài liệu; nên nạp theo lĩnh vực (nội dung, khách hàng, KPI, pháp lý, quy trình).
4. Bấm **Bật học tự động** hoặc **Học một bước ngay** sau khi đã bật. Màn hình hiển thị tài liệu, số đoạn, bài đã đào tạo, token và USD/ngày.
5. Các agent tự truy xuất và lưu bài học theo nguồn; kết quả vẫn cần kiểm tra trước khi áp dụng quyết định lớn.

> Không hứa tiêu hết 10M token/ngày nếu không có đủ tài liệu chất lượng hoặc ngân sách. Không tự đọc Facebook API, không tự quét Facebook, không tự đăng bài.

## V1.4.0 – Claude-only, model tự chọn để tiết kiệm chi phí

- Màn hình **Cài đặt API** chỉ còn khóa **Anthropic Claude**; không có lựa chọn Gemini, Groq hoặc dropdown model. Mã nguồn hiện không gọi Gemini/Groq. Các khóa cũ vẫn được giữ nguyên trong kho mã hóa để tránh mất dữ liệu khi nâng cấp nhưng không còn được dùng.
- Mỗi agent chọn model **theo luật không tốn API**: Haiku 5.5 cho việc thường, Sonnet 5.5 cho vấn đề phức tạp/rủi ro; Haiku được phép yêu cầu nâng cấp **một lần** nếu không xử lý được. Không có vòng lặp gọi model không giới hạn.
- Ngân sách USD/ngày và giới hạn lượt gọi/ngày áp dụng với toàn bộ lời gọi Claude, kể cả khi nâng cấp. Nếu không đủ ngân sách, nhiệm vụ báo lỗi thay vì tự đổi sang model chất lượng thấp cho nội dung rủi ro.
- **Bộ não nhân viên** hiển thị lịch sử model và chi phí ước tính theo từng agent. Cache cục bộ vẫn tránh lặp yêu cầu giống hệt. Model có thể không khả dụng nếu tài khoản Anthropic chưa được cấp quyền; dùng nút **Kiểm tra Claude đã lưu** để kiểm tra mà không phát sinh token suy luận.
- Cấu hình cũ được đọc an toàn; lựa chọn provider/model cũ không còn tác động tới routing. Không xóa SQLite, bộ nhớ agent, khóa mã hóa hay Firefox profiles khi cập nhật.
- Bảng giá và model IDs có thể thay đổi; dự toán trong ứng dụng không phải hóa đơn Anthropic. Kiểm tra bảng giá mới tại <https://platform.claude.com/docs/en/about-claude/pricing>.

## Bản vá V1.3.2 – lỗi múi giờ trên Windows

- Thêm dependency `tzdata` vào `requirements.txt` để Python (bao gồm 3.14) tìm được `Asia/Ho_Chi_Minh`.
- Bộ tính ngân sách Claude có dự phòng múi giờ UTC+07:00 nếu dữ liệu IANA không tồn tại, tránh lỗi `/api/bootstrap` HTTP 500 khi mở giao diện.
- Công cụ `diagnose_windows.bat` kiểm tra tình trạng timezone/tzdata.
- Nếu đang chạy V1.3.1, thực hiện `git pull origin main` rồi **đóng cửa sổ máy chủ cũ** và khởi động lại bằng `start_windows.bat` để tự cài dependency. Có thể sửa ngay bằng `.venv\Scripts\python.exe -m pip install tzdata` trong thư mục dự án.

## Chạy trên Windows

1. Cài **Python 3.11+**. Firefox chưa cần cài sẵn: phần mềm có chức năng kiểm tra, tải và mở bộ cài chính thức từ Mozilla khi bạn đồng ý. Khi cài Python nhớ chọn “Add to PATH” hoặc cài Python Launcher (`py`).
2. Giải nén thư mục `ai-fanpage-company` vào ổ đĩa bất kỳ.
3. Nhấp đúp `start_windows.bat`. Lần đầu script sẽ tạo `.venv` và cài thư viện (cần Internet).
4. Trình duyệt mặc định mở `http://127.0.0.1:8765` để sử dụng phần mềm. **Chỉ chạy một instance server** trên cùng port 8765.
5. Vào **Cài đặt** và nhập Claude API key để sử dụng agent AI thực. Nếu không có key, CEO sẽ giữ yêu cầu ở trạng thái chờ, không bịa kết quả.

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
4. **Cài đặt AI** → nhập duy nhất Claude API key. Model do phần mềm tự chọn; không có hộp chọn Gemini/Groq hay chọn model Claude.
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
- AI: Claude Messages API qua HTTPS. Bộ định tuyến chọn Haiku 5.5 cho nhiệm vụ thường, Sonnet 5.5 cho nhiệm vụ khó/rủi ro. Không cần chọn model; có giới hạn lượt gọi và USD/ngày.
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

## V1.3 — Bộ não riêng cho 9 agent + Claude API có hạn mức

- **Mỗi agent có trí nhớ độc lập:** `agent_memories` phân vùng theo `agent_id`, nguồn bài học và mức tin cậy (`unverified`/`verified`). Truy xuất theo từ khóa ở máy chủ, không gửi toàn bộ lịch sử lên Claude và không cần vector API.
- **Học theo sự kiện 24/24 khi máy chủ hoạt động:** các nhiệm vụ hoàn tất và KPI nhập vào tạo `agent_learning_events`; dịch vụ nền đọc sự kiện và tổng kết bộ nhớ nội bộ mỗi phút, chi phí Claude lúc không có công việc **0 USD**. Khi tắt máy, hệ thống ngừng; bật lại xử lý sự kiện còn chờ. Không có khả năng tự duyệt Facebook hoặc tự đọc Insights.
- **Claude tự chọn model:** Claude là nhà cung cấp duy nhất; từng agent tự dùng Haiku hoặc Sonnet tùy nhiệm vụ. Model nhẹ mặc định `claude-haiku-5-5`, model nâng cấp `claude-sonnet-5-5`. Nếu model nhẹ trả `NEED_CLAUDE`, hệ thống chỉ thử **một lần nâng cấp**. Không có vòng gọi Claude vô hạn.
- **Chi phí và bảo mật:** Claude API key được mã hóa trong dữ liệu cục bộ, không được đưa lên Git. `claude_usage` lưu số token và tiền ước tính; hai hạn mức USD/ngày (toàn công ty và mỗi agent) có dự trù ngân sách trước cuộc gọi để ngăn worker vượt số tiền được cấu hình. Ngày được tính theo giờ Việt Nam. Số tiền hiển thị là **ước tính**, không thay hóa đơn thực tế Anthropic. Vẫn cần giới hạn sử dụng và cảnh báo trên Anthropic Console.
- **Tiết kiệm thêm:** giới hạn context và output; dùng local memory; tái sử dụng phản hồi với đầu vào *hoàn toàn giống nhau* trong 6 giờ, tách biệt theo agent; bật prompt caching cho prompt ổn định và đủ dài. Anthropic hỗ trợ Batches giảm 50% cho công việc không cần phản hồi ngay, nhưng **V1.3 chưa triển khai Batch API**.
- **Giao diện:** menu `🧠 Bộ não nhân viên` hiển thị bộ nhớ, số lượt học, USD/ngày và lịch sử lựa chọn model thật. Mục Cài đặt chỉ có Claude API key, giới hạn ngân sách/lượt gọi, cache và tự chạy agent.

### Cách sử dụng Claude

1. Chạy `start_windows.bat`, vào **Cài đặt** → **Kết nối Claude AI**.
2. Nhập duy nhất `Claude API key` (không nhập trong chat hoặc commit lên Git), bấm **Lưu cài đặt**. Có thể bấm **Kiểm tra Claude đã lưu** để gọi Models API (không tốn token sinh văn bản). Phần mềm tự chọn Haiku/Sonnet và tự nâng cấp tối đa một lần khi Haiku không thể hoàn thành.
3. Đặt ngân sách mặc định `1 USD/ngày` cho công ty và `0.25 USD/ngày` cho mỗi agent; có thể chỉnh giảm về 0 để khóa toàn bộ cuộc gọi Claude.
4. Vào **Bộ não nhân viên** để xem kinh nghiệm riêng, model đã gọi gần đây và chi phí. Bấm **Xử lý bài học chờ** để cập nhật ngay, không tốn token.

**Giới hạn quan trọng:** Một agent không tự tạo kiến thức mới từ Internet nếu không được cấp nguồn đáng tin cậy. Kết quả công việc và số liệu nhập thủ công vẫn được đánh dấu chưa xác minh. Chi phí thực có thể thay đổi theo giá và điều khoản Anthropic; báo cáo chỉ theo các lời gọi đi qua phần mềm, không bao gồm các ứng dụng khác dùng cùng API key. Để bộ nhớ chạy xuyên ngày đêm, máy chủ cài phần mềm phải hoạt động liên tục (hoặc triển khai trên máy chủ luôn bật).

Tài liệu Anthropic: [Messages API](https://platform.claude.com/docs/en/api/http/messages), [Pricing](https://platform.claude.com/docs/en/about-claude/pricing), [Prompt caching](https://platform.claude.com/docs/en/build-with-claude/prompt-caching), [Message Batches](https://platform.claude.com/docs/en/build-with-claude/batch-processing).

## Khắc phục lỗi khởi động – V1.3.1

1. Trên Windows, cập nhật mã nguồn bằng `git pull origin main` và chạy lại `start_windows.bat`.
2. Nếu phần mềm báo lỗi hoặc tự đóng, nhấp đúp `diagnose_windows.bat`. Công cụ chỉ kiểm tra thư viện Python, tình trạng cổng và nhật ký khởi động, không đọc API key hay cookie Facebook.
3. Đọc `diagnostics.txt` trong thư mục dự án; chi tiết máy chủ nằm tại `%LOCALAPPDATA%\AI-Fanpage-Company\logs\startup.log`.
4. Nếu giao diện trống, mở URL được in trong cửa sổ console (có thể là cổng `8766` nếu `8765` đã bận) và nhấn `Ctrl+Shift+R` để tải lại tài nguyên.
5. Nếu Python không được nhận diện, hãy cài Python 3.11+ với tùy chọn **Add Python to PATH**, rồi chạy lại. Script mới thử cả `py -3` và `python`.

**Không xóa** `%LOCALAPPDATA%\AI-Fanpage-Company`, đặc biệt `company.sqlite3`, `profiles`, `api_secrets.json.enc` và `local_secret.key`: đây là dữ liệu, thông tin phiên Firefox và khóa API đã mã hóa của bạn. Không chia sẻ những tệp này hoặc mật khẩu, cookie, API key khi báo lỗi.

Những thay đổi này tăng khả năng phát hiện lỗi chung; chưa xác định nguyên nhân cụ thể của lỗi Windows khi chưa có log hoặc ảnh màn hình từ máy người dùng.


## V1.12 – Bộ thu thập kiến thức có quyền sử dụng

- Học viện có nút **Nạp giáo trình cho 9 agent**: 27 giáo trình marketing tiếng Việt do dự án tự biên soạn, chỉ trích dẫn URL nguồn. Các giáo trình được đưa vào hàng đợi MiraiAPI theo chuyên môn. Nạp lần hai không nhân đôi tài liệu.
- **Tải tài liệu mở**: chỉ xét một danh mục URL Google Developers đã được chọn và có tuyên bố giấy phép CC BY 4.0; trước khi tải kiểm tra HTTPS, miền, robots.txt, content-type, giới hạn dung lượng, tuyên bố giấy phép tại trang, và lưu nguồn/ghi nhận lỗi. Không quét Facebook, không bỏ qua đăng nhập, không chạy crawler toàn miền.
- Danh mục Meta Blueprint và học liệu có quyền hạn chế chỉ lưu liên kết, không sao chép toàn văn. Tải lại các nguồn bị chặn không tự động diễn ra.
- Số lượng "đã tải" trên màn hình là số tài liệu thực tế tải thành công. Kế hoạch học không cam kết dùng hết 10 triệu quota vì còn phụ thuộc nguồn, ngân sách và giới hạn của MiraiAPI.
- Môi trường kiểm thử offline không thể tải nguồn Internet; khi sử dụng trên Windows có Internet, bấm **Tải tài liệu mở được phép** rồi xem trạng thái của từng nguồn.
