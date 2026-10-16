# DurianCare — Sổ Vườn Sầu Riêng Thông Minh

Hệ thống quản lý trang trại sầu riêng thông minh, an toàn VietGAP / GlobalGAP và phục vụ xuất khẩu chính ngạch (Việt Nam - Trung Quốc & EU).

**Stack:** Python 3.12 · Django 5.2 + DRF · PostgreSQL / SQLite · React (Responsive & PWA) · Celery 5.6 + Redis · Docker Compose

---

## 1. Khởi động nhanh

### 1.1. Chạy Backend (SQLite — Không cần cài thêm DB)
```bash
cd backend
python -m venv ../.venv
..\.venv\Scripts\pip install -r requirements.txt
python manage.py migrate
python manage.py test              # 138 tests passing (100% OK)
python manage.py runserver 8000
```
- **Swagger API Docs:** http://localhost:8000/api/docs/
- **Django Admin:** http://localhost:8000/admin/

### 1.2. Chạy Frontend React (PWA)
```bash
cd frontend
npm install
npm run dev                        # http://localhost:3000
```

### 1.3. Chạy Toàn Bộ Bằng Docker Compose (Production-ready)
```bash
cp .env.example .env
docker compose up --build
```
Dịch vụ bao gồm:
- `db` (PostgreSQL 16)
- `redis` (Redis 7)
- `backend` (Django + Gunicorn)
- `celery-worker` (Xử lý tác vụ nền)
- `celery-beat` (Lập lịch kiểm tra PHI & nhắc việc hằng ngày)
- `frontend` (React PWA trên nền Nginx Alpine)

---

## 2. Các Tính Năng Đã Hoàn Thiện

| Phân hệ | Tính năng & Quy tắc nghiệp vụ |
|---|---|
| **Xác thực & Vườn** | JWT, đăng nhập SĐT, đa vườn (multi-farm), phân quyền RBAC (`OWNER`, `WORKER`, `ADVISOR`), mã số vùng trồng, quản lý lô đất & mùa vụ (`BR-01, 02, 04, 20, 21`). |
| **Nhật ký canh tác & BVTV** | Ghi nhật ký phân bón, thuốc BVTV, tự tính chi phí, kiểm tra danh mục sầu riêng, bắt buộc số ngày cách ly `phi_days` (`BR-03, 05, 06, 07`). |
| **Thu hoạch & An toàn PHI** | Quản lý lô `/batches/` & `/harvest-batches/`, đếm ngày an toàn PHI, chặn thu hoạch non, OWNER override kèm lý do & audit log, tồn kho theo phẩm cấp `GRADE_1/2/3/REJECT` (`BR-08..11`). |
| **Kiểm nghiệm & Xuất khẩu** | `LabTest` đầy đủ chỉ tiêu `analyte`, `result_value`, `limit_value`, `valid_until`, trạng thái `VOIDED`. Phân quyền nhập cho `OWNER`, `ADVISOR`, `WORKER`. Kiểm tra điều kiện xuất khẩu khắt khe (BR-13): phẩm cấp Loại 1/2, kiểm nghiệm còn hạn, nồng độ Cadmium $\le 0.05$ ppm. |
| **Bán hàng & Công nợ** | Bán hàng `Sale`, khách mua `Buyer`, row lock chống deadlock `select_for_update`, trừ tồn kho tự động, thu tiền `/payments/`, hủy phiếu hoàn tồn kho (`BR-14, 15, 17, 18, 19`). |
| **Báo cáo quản trị (App `reports`)** | 1. Lãi lỗ (P&L)<br>2. Giá thành / kg (`BR-24`): chi phí trực tiếp + phân bổ chi phí chung theo diện tích đất (có bộ dữ liệu mẫu tính tay mục 16.2 đặc tả)<br>3. Công nợ người mua (`Buyer`)<br>4. Tồn kho sầu riêng theo Grade<br>5. Cảnh báo an toàn cách ly PHI. |
| **Công việc & Thông báo (App `tasks`)** | Quản lý việc làm vườn, tự động sinh việc chu kỳ tiếp theo khi hoàn thành (`BR-22`), bảo vệ việc hệ thống không cho sửa (`BR-23`), thông báo trong app & Celery task tự động. |
| **Frontend Web App & PWA** | Giao diện React hiện đại, trực quan, hỗ trợ cài đặt PWA (offline cache, service worker, manifest), tương thích tốt trên di động cho nhà vườn. |

---

## 3. Kiểm Thử (Automated Tests)

Bộ kiểm thử tự động gồm **138 test cases** phủ toàn bộ các quy tắc nghiệp vụ:
```bash
cd backend
python manage.py test
```
```text
Ran 138 tests in 4.165s
OK
```

---

## 4. Tài Liệu Nghiệp Vụ
- [Đặc tả chi tiết hệ thống (dac-ta.md)](docs/dac-ta.md): Chi tiết từ BR-01 đến BR-24, Ma trận quyền, Mục 16 (Báo cáo & dữ liệu tính tay 16.2), Mục 22 (Quy tắc đếm PHI & Tiêu chuẩn xuất khẩu BR-13), và chuẩn hóa URL.
- [Ghi chú nội bộ](docs/internal/): Lịch sử đối chiếu và kế hoạch triển khai.
