# Menu

Static Workflow 가 실행할 수 있는 Recipe 목록이다.
사용자 요청은 여기 적힌 Recipe 중 하나로만 해석한다.

이 문서는 사람이 읽으라고 둔 사본이다.
LLM 에 Context 로 전달되는 것은 [menu.yaml](menu.yaml) 뿐이므로, 한쪽을 고치면 다른 쪽도 같이 고친다.

## 목차

| Recipe ID | 기능 | 실행 순서 |
| --- | --- | --- |
| recipe_001 | CCTV 동영상을 불러온다. | load_cctv |
| recipe_002 | CCTV 동영상을 불러와 동영상에서 군중을 분석한다. | load_cctv ➜ analyze_crowd |
| recipe_003 | CCTV 동영상을 불러와 동영상에서 군중을 분석하고 분석 결과를 Word 문서로 생성한다. | load_cctv ➜ analyze_crowd ➜ generate_word |
| recipe_004 | CCTV 동영상을 불러와 동영상에서 군중을 분석하고 분석 결과를 PPT 문서로 생성한다. | load_cctv ➜ analyze_crowd ➜ generate_ppt |
| recipe_005 | CCTV 동영상을 불러와 동영상에서 군중을 분석하고 분석 결과를 관리자에게 전달한다. | load_cctv ➜ analyze_crowd ➜ notify_manager |
| recipe_006 | 이미지를 불러온다. | load_image |
| recipe_007 | 이미지를 불러와 이미지에서 균열을 분석한다. | load_image ➜ detect_crack |
| recipe_008 | 이미지를 불러와 이미지에서 균열을 분석하고 분석 결과를 Word 문서로 생성한다. | load_image ➜ detect_crack ➜ generate_word |
| recipe_009 | 이미지를 불러와 이미지에서 균열을 분석하고 분석 결과를 PPT 문서로 생성한다. | load_image ➜ detect_crack ➜ generate_ppt |
| recipe_010 | 이미지를 불러와 이미지에서 균열을 분석하고 분석 결과를 관리자에게 전달한다. | load_image ➜ detect_crack ➜ notify_manager |

---

# Recipe 001

## 기능

CCTV 동영상을 불러온다.

## 실행 순서

### 1

Node:
- load_cctv

Input:
- 없음

Output:
- Video

---

# Recipe 002

## 기능

CCTV 동영상을 불러와 동영상에서 군중을 분석한다.

## 실행 순서

### 1

Node:
- load_cctv

Input:
- 없음

Output:
- Video

### 2

Node:
- analyze_crowd

Input:
- Video

Output:
- AnalysisResult

---

# Recipe 003

## 기능

CCTV 동영상을 불러와 동영상에서 군중을 분석하고 분석 결과를 Word 문서로 생성한다.

## 실행 순서

### 1

Node:
- load_cctv

Input:
- 없음

Output:
- Video

### 2

Node:
- analyze_crowd

Input:
- Video

Output:
- AnalysisResult

### 3

Node:
- generate_word

Input:
- AnalysisResult

Output:
- Report

---

# Recipe 004

## 기능

CCTV 동영상을 불러와 동영상에서 군중을 분석하고 분석 결과를 PPT 문서로 생성한다.

## 실행 순서

### 1

Node:
- load_cctv

Input:
- 없음

Output:
- Video

### 2

Node:
- analyze_crowd

Input:
- Video

Output:
- AnalysisResult

### 3

Node:
- generate_ppt

Input:
- AnalysisResult

Output:
- Report

---

# Recipe 005

## 기능

CCTV 동영상을 불러와 동영상에서 군중을 분석하고 분석 결과를 관리자에게 전달한다.

## 실행 순서

### 1

Node:
- load_cctv

Input:
- 없음

Output:
- Video

### 2

Node:
- analyze_crowd

Input:
- Video

Output:
- AnalysisResult

### 3

Node:
- notify_manager

Input:
- AnalysisResult

Output:
- Notification

---

# Recipe 006

## 기능

이미지를 불러온다.

## 실행 순서

### 1

Node:
- load_image

Input:
- 없음

Output:
- Image

---

# Recipe 007

## 기능

이미지를 불러와 이미지에서 균열을 분석한다.

## 실행 순서

### 1

Node:
- load_image

Input:
- 없음

Output:
- Image

### 2

Node:
- detect_crack

Input:
- Image

Output:
- AnalysisResult

---

# Recipe 008

## 기능

이미지를 불러와 이미지에서 균열을 분석하고 분석 결과를 Word 문서로 생성한다.

## 실행 순서

### 1

Node:
- load_image

Input:
- 없음

Output:
- Image

### 2

Node:
- detect_crack

Input:
- Image

Output:
- AnalysisResult

### 3

Node:
- generate_word

Input:
- AnalysisResult

Output:
- Report

---

# Recipe 009

## 기능

이미지를 불러와 이미지에서 균열을 분석하고 분석 결과를 PPT 문서로 생성한다.

## 실행 순서

### 1

Node:
- load_image

Input:
- 없음

Output:
- Image

### 2

Node:
- detect_crack

Input:
- Image

Output:
- AnalysisResult

### 3

Node:
- generate_ppt

Input:
- AnalysisResult

Output:
- Report

---

# Recipe 010

## 기능

이미지를 불러와 이미지에서 균열을 분석하고 분석 결과를 관리자에게 전달한다.

## 실행 순서

### 1

Node:
- load_image

Input:
- 없음

Output:
- Image

### 2

Node:
- detect_crack

Input:
- Image

Output:
- AnalysisResult

### 3

Node:
- notify_manager

Input:
- AnalysisResult

Output:
- Notification
