# Hướng dẫn cài đặt Market Research Tool

## Bước 1: Chuẩn bị credentials

Sao chép file `.env.example` thành `.env` và điền thông tin:

```bash
cp .env.example .env
nano .env
```

### Lấy Shopee Affiliate credentials:
1. Vào https://affiliate.shopee.vn/account/apiManage
2. Tạo App → lấy **App ID** và **Secret Key**
3. Điền vào `.env`

### Lấy Facebook Access Token:
1. Vào https://developers.facebook.com → Tạo App
2. Thêm product: **Facebook Login**
3. Vào Graph API Explorer → lấy Access Token
4. Cần quyền: `pages_read_engagement`, `ads_read`, `instagram_basic`
5. Điền vào `.env`

---

## Bước 2: Chạy với Docker (khuyến nghị)

```bash
curl -fsSL https://get.docker.com | sh
cd market_research
docker-compose up -d
docker-compose logs -f app
```

Mở trình duyệt: **http://server_ip:8000**

---

## Bước 3: Chạy thủ công (nếu không dùng Docker)

```bash
cd backend
pip install -r requirements.txt
playwright install chromium
cp ../.env.example .env
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

---

## Cách dùng cơ bản

1. **Dashboard**: Xem tổng quan trending từ tất cả nguồn
2. **Shopee**: Tìm sản phẩm theo từ khóa, xem top trending
3. **Facebook Ads**: Tìm ads đối thủ, phân tích comments
4. **Instagram**: Tìm posts theo hashtag
5. **Từ khóa**: Xem từ khóa nổi bật từ tất cả nguồn
6. **⚡ Crawl ngay**: Cập nhật dữ liệu mới nhất

Hệ thống tự động crawl mỗi **6 giờ/lần**.

---

## Cấu trúc project

```
market_research/
├── backend/
│   ├── app/
│   │   ├── scrapers/    # Crawl Shopee, Facebook, Instagram
│   │   ├── analyzers/   # NLP + Trend scoring
│   │   ├── routers/     # API endpoints
│   │   └── models/      # Database models
│   └── Dockerfile
├── frontend/
│   └── index.html       # Dashboard UI
├── data/                # SQLite database (tự tạo)
├── .env                 # Credentials (KHÔNG commit lên git)
└── docker-compose.yml
```
