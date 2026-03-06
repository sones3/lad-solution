# Document Template Index Extractor (MVP)

Simple full-stack app for template-driven extraction:

- Create a template from a PNG/JPG image.
- Draw named zones where indexes/fields should be extracted.
- Save templates locally.
- Upload a new image and extract fields by aligning it to the template with ORB.
- See visual alignment previews (template, uploaded, aligned, overlay) after each extraction.
- Extraction uses full-page word OCR on the aligned image, then keeps words whose boxes intersect each template zone.
- Extraction screen includes a before/after slider (template vs aligned upload) and overlayed OCR/zone boxes for debugging.
- You can enable Wolf binarization (doxapy) per template and see binarized template/uploaded previews during extraction.

## Stack

- Frontend: React + TypeScript + Vite
- Backend: FastAPI + OpenCV + pytesseract
- Storage: local JSON + files in `backend/data`

## Requirements

- Node.js 20+
- Python 3.10+
- Tesseract OCR installed and available on `PATH`
- `doxapy` (installed from `requirements.txt`) for Wolf binarization

## Run frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend runs at `http://localhost:5173`.

## Run backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Backend runs at `http://localhost:8000`.

## API overview

- `GET /health`
- `POST /templates` (multipart: `name`, `zones` as JSON string, `image`, `useWolfBinarization`)
- `GET /templates`
- `GET /templates/{template_id}`
- `PUT /templates/{template_id}`
- `DELETE /templates/{template_id}`
- `POST /extract` (multipart: `templateId`, `image`, optional `debug`)

## Notes

- Supported input formats in v1: PNG/JPG only.
- Aligned debug images are saved to `backend/data/debug` when `debug=true`.
- No automated test suite is included in this scope.
