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