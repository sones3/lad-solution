# Document Template Index Extractor (MVP)

Simple full-stack app for template-driven extraction:

- Create a template from a PNG/JPG image.
- Draw named zones where indexes/fields should be extracted.
- Save templates locally.
- Upload a new image and extract fields by aligning it to the template with ORB.
- Upload a PDF and detect logical document starts by matching each page against a template with ORB.
- Choose between ORB alignment, a paper-style stable-keypoint detector, and a recommended hybrid detector when running logical separation.
- Logical separation streams page-by-page diagnostics to the UI while the PDF is being processed.
- Upload a lot PDF plus CSV and reconcile separated documents against CSV rows with OCR + fuzzy matching.
- See visual alignment previews (template, uploaded, aligned, overlay) after each extraction.
- Extraction uses full-page word OCR on the aligned image, then keeps words whose boxes intersect each template zone.
- Extraction screen includes a before/after slider (template vs aligned upload) and overlayed OCR/zone boxes for debugging.
- You can enable Wolf binarization (doxapy) per template and see binarized template/uploaded previews during extraction.
- You can choose OCR engine at extraction time: `tesseract` or `PaddleOCR v5 mobile (fr)`.
- PaddleOCR is initialized once on backend startup and reused for extraction requests.

## Stack

- Frontend: React + TypeScript + Vite
- Backend: FastAPI + OpenCV + pytesseract
- Storage: local JSON + files in `backend/data`

## Requirements

- Node.js 20+
- Python 3.10+
- Tesseract OCR installed and available on `PATH`
- `doxapy` (installed from `requirements.txt`) for Wolf binarization
- PaddleOCR runtime dependencies from `requirements.txt` (`paddleocr`, `paddlepaddle`)
  - oneDNN is enabled for faster PaddleOCR CPU inference.
  - PaddleOCR input is downscaled before prediction for better latency.

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
- `POST /templates` (multipart: `name`, `zones` as JSON string, `paperIgnoreRegions` as JSON string, `image`, `useWolfBinarization`)
- `GET /templates`
- `GET /templates/{template_id}`
- `PUT /templates/{template_id}`
- `DELETE /templates/{template_id}`
- `POST /extract` (multipart: `templateId`, `image`, optional `debug`)
- `POST /extract` (multipart: `templateId`, `image`, `ocrEngine`, optional `debug`)
- `POST /separate-logically` (multipart: `templateId`, `pdf`, optional `method` = `orb`, `paper`, or `hybrid`, optional `threshold` in `[0,1]`)
- `POST /separate-logically/stream` (multipart: `templateId`, `pdf`, optional `method` = `orb`, `paper`, or `hybrid`, optional `threshold` in `[0,1]`)
- `POST /lots/analyze` (multipart: `pdf`, `csv`, optional OCR tuning fields)
- `POST /lots/analyze/stream` (multipart: `pdf`, `csv`, optional OCR tuning fields)

## Notes

- Extraction input formats: PNG/JPG.
- Logical separation input format: PDF.
- Aligned debug images are saved to `backend/data/debug` when `debug=true`.
- Logical separation analyzes PDF pages in memory and does not write split PDFs.
- Logical separation page diagnostics include whether Wolf binarization was applied for each page.
- The recommended hybrid method uses anchor-region visual fingerprints as a fast gate, then confirms matches with ORB; it does not use OCR.
- The paper method builds a masked template artifact once from the template image, synthesizes distortions, scores stable ORB keypoints, and uses that reduced descriptor set during logical separation.
- Templates now support separate paper ignore regions for varying fields that should be excluded from paper-method keypoint selection.
- The logical separation UI lets you choose the detection threshold before processing.
- Lot analysis uses OCR-keyword separation on the top 50% of each page with Otsu binarization, `fra` OCR, and exact numeric plus fuzzy text matching.
- Lot OCR can run with multiple worker threads while preserving ordered page/document streaming in the UI.
- Lot validation is strict: count mismatches, ambiguous rows, duplicate assignments, or missing matches keep the lot blocked.
- No automated test suite is included in this scope.
