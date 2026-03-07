# Integration Handoff Recap

This document summarizes all implemented changes so the next agent can integrate the work into another app quickly.

## Goal Achieved

Built a template-driven document extraction MVP with:

- React frontend to create/edit templates and extraction zones.
- FastAPI backend for template storage and extraction.
- ORB-based document alignment to template coordinates.
- Zone extraction based on full-page word OCR + geometric intersection.
- Optional Wolf binarization (doxapy) at template level.
- OCR engine selection at runtime (`tesseract` or `paddleocr`).
- Visual debug views (alignment slider, OCR boxes, zone boxes, OCR text).

---

## Current Architecture

### Frontend (`frontend/`)

- React + TypeScript + Vite.
- Main views:
  - Templates list
  - Template editor
  - Extraction page
- API modules:
  - `frontend/src/api/templates.ts`
  - `frontend/src/api/extraction.ts`

### Backend (`backend/`)

- FastAPI app in `backend/app/main.py`
- Local file/JSON persistence in `backend/data`
- Static data exposed under `/data`.

---

## Implemented Functional Flow

1. User creates a template image and draws named zones.
2. Template saved with zone coordinates (template coordinate system).
3. User runs extraction with:
   - template selection,
   - uploaded image,
   - OCR engine selection.
4. Backend aligns uploaded image to template using ORB homography.
5. OCR runs on aligned image (full page, word-level outputs).
6. For each zone, words intersecting zone are selected and merged.
7. Extracted values + confidence + warnings are returned.
8. Frontend shows debug visualizations.

---

## Key Backend Changes

### API

- `POST /templates` accepts multipart:
  - `name`
  - `zones` (JSON string)
  - `image`
  - `useWolfBinarization` (boolean)

- `PUT /templates/{id}` accepts JSON:
  - `name`
  - `zones`
  - `useWolfBinarization`

- `POST /extract` accepts multipart:
  - `templateId`
  - `image`
  - `ocrEngine` (`tesseract` or `paddleocr`)
  - `debug` (optional)

### OCR Engines

- Implemented in `backend/app/services/ocr_service.py`
- Tesseract path: `pytesseract.image_to_data`
- Paddle path:
  - Uses `PaddleOCR.predict(...)`
  - Parses `rec_texts`, `rec_scores`, `rec_boxes`
  - Handles ndarray/list payload variants safely

### Paddle Initialization at Startup

- Implemented singleton-like initialization in:
  - `backend/app/services/paddle_engine.py`
- Called from FastAPI startup hook in `backend/app/main.py`
- Paddle config:
  - `lang="fr"`
  - `text_detection_model_name="PP-OCRv5_mobile_det"`
  - `text_recognition_model_name="PP-OCRv5_mobile_rec"`
  - `use_doc_orientation_classify=False`
  - `use_doc_unwarping=False`
  - `use_textline_orientation=False`
  - `enable_mkldnn=True`

### Performance Optimization Applied

- Paddle OCR now downsamples before prediction:
  - `PADDLE_MAX_LONG_SIDE = 1600`
- Bboxes are scaled back to original aligned coordinates before zone matching.

### Binarization

- `backend/app/services/binarization.py`
- Wolf binarization via doxapy with params:
  - `window=95`
  - `k=0.1`
- Applied to both template and uploaded images when template toggle enabled.

---

## Key Frontend Changes

### Template Editor

- File: `frontend/src/pages/TemplateEditorPage.tsx`
- Added button toggle:
  - `Wolf binarization: Enabled/Disabled`

### Extraction Page

- File: `frontend/src/pages/ExtractionPage.tsx`
- Added OCR engine selector:
  - `Tesseract`
  - `PaddleOCR v5 mobile (fr)`
- Added alignment compare slider (template vs aligned uploaded)
- Added debug overlays on aligned image:
  - OCR word bboxes (cyan)
  - zone rectangles (orange)
- Added full-page OCR text display and OCR word list table.
- Added optional binarized previews panel:
  - template Wolf image
  - uploaded Wolf image

### Types Updated

- File: `frontend/src/types/template.ts`
- Added/updated:
  - `Template.useWolfBinarization`
  - extraction `ocrEngine`
  - debug word structures and matched word IDs
  - preview binarized image paths

---

## Data/Model Contract Highlights

### Template model

- `id`, `name`, `imagePath`, `imageWidth`, `imageHeight`
- `zones[]`
- `useWolfBinarization`
- `createdAt`, `updatedAt`, `version`

### Extract response

- `templateId`
- `ocrEngine`
- `alignment` (`success`, `inlierRatio`, `matchesUsed`, `warnings`)
- `preview` paths (`template`, `uploaded`, `aligned`, `overlay`, optional binarized)
- `debug` with image dimensions + OCR word boxes
- `fields` with text/confidence/warning/matchedWordIds
- `errors`

---

## Files Most Relevant for Integration

- Backend
  - `backend/app/main.py`
  - `backend/app/api/templates.py`
  - `backend/app/api/extraction.py`
  - `backend/app/services/orb_align.py`
  - `backend/app/services/ocr_service.py`
  - `backend/app/services/paddle_engine.py`
  - `backend/app/services/binarization.py`
  - `backend/app/models/template_models.py`
  - `backend/app/models/extraction_models.py`
  - `backend/requirements.txt`

- Frontend
  - `frontend/src/App.tsx`
  - `frontend/src/pages/TemplateEditorPage.tsx`
  - `frontend/src/pages/ExtractionPage.tsx`
  - `frontend/src/components/ImageCanvas.tsx`
  - `frontend/src/components/ZoneList.tsx`
  - `frontend/src/api/templates.ts`
  - `frontend/src/api/extraction.ts`
  - `frontend/src/types/template.ts`
  - `frontend/src/index.css`

---

## Known Caveats

- Paddle runtime compatibility can vary by environment.
  - oneDNN is enabled for speed, but some environments may still hit PIR/oneDNN errors.
  - If this occurs in target app, add runtime fallback (retry with oneDNN disabled or fallback to Tesseract).
- Extraction debug previews currently write files on each run; this adds I/O overhead.
- No automated tests were added by request.

---

## Dependency Notes

Backend dependencies include:

- `opencv-python`
- `pytesseract`
- `doxapy`
- `paddleocr`
- `paddlepaddle`
- `fastapi`, `uvicorn`, `python-multipart`, `pydantic`, `numpy`

Make sure Tesseract binary is installed and available in `PATH`.

---

## Suggested Integration Order (for next agent)

1. Port backend model/API contracts first.
2. Port extraction pipeline services (`orb_align`, `ocr_service`, `paddle_engine`, `binarization`).
3. Validate `/extract` with both OCR engines.
4. Port frontend extraction page controls (OCR selector + debug views).
5. Port template toggle for Wolf binarization.
6. Only then tune performance and UX in destination app.
