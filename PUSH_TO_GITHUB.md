# Đẩy AI Fanpage Company lên GitHub

Repository Git đã được khởi tạo và có commit đầu tiên, không chứa SQLite, cookie, Firefox profiles, khóa API hoặc dữ liệu đăng nhập.

1. Trên GitHub tạo repository mới, ví dụ tên `ai-fanpage-company`; nên chọn **Private**. Không bật "Add a README", `.gitignore` hoặc license vì project đã có file này.
2. Giải nén gói ZIP này rồi mở Command Prompt hoặc PowerShell trong thư mục project.
3. Dán URL HTTPS của repository vừa tạo vào lệnh bên dưới:

```powershell
git remote add origin https://github.com/USERNAME/REPOSITORY.git
git push -u origin main
```

GitHub có thể yêu cầu đăng nhập bằng Git Credential Manager / trình duyệt hoặc token quyền phù hợp. Không gửi token GitHub cho người khác hay dán vào mã nguồn.

Nếu repository đã có README/commit, cần kiểm tra lịch sử trước khi đẩy; không chạy `git push --force`.

Lưu ý: Mã nguồn là bản MVP V1, chưa có auto-publish Facebook và chưa kiểm thử production cho 100 Page.
