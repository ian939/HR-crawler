import os
import pandas as pd
from slack_sdk import WebClient
from datetime import datetime

# 1. 환경 변수 설정
SLACK_TOKEN = os.environ.get("SLACK_BOT_TOKEN")
CANVAS_ID = os.environ.get("SLACK_CANVAS_ID")
CSV_PATH = "job_listings_all.csv"  # 변경된 파일명

def update_slack_canvas():
    if not SLACK_TOKEN or not CANVAS_ID:
        print("❌ 에러: SLACK_BOT_TOKEN 또는 SLACK_CANVAS_ID가 설정되지 않았습니다.")
        return

    client = WebClient(token=SLACK_TOKEN)

    try:
        # 2. 새로운 CSV 파일 읽기
        if not os.path.exists(CSV_PATH):
            print(f"❌ 에러: {CSV_PATH} 파일을 찾을 수 없습니다.")
            return
            
        df = pd.read_csv(CSV_PATH)
        # 최신 등록일 순으로 정렬 (필요 시)
        df = df.sort_values(by='first_seen', ascending=False)
        
        today = datetime.now().strftime('%Y-%m-%d')
        
        # 3. 캔버스용 마크다운 생성 (회사명/공고제목/경력/링크/최초등록일)
        markdown_text = f"# 🚀 채용 정보 리스트 ({today})\n\n"
        markdown_text += f"현재 DB에 저장된 공고는 총 **{len(df)}개**입니다.\n\n---\n\n"
        
        # 테이블 헤더 구성
        markdown_text += "| 회사명 | 공고 제목 | 경력 | 등록일 | 링크 |\n"
        markdown_text += "|:---|:---|:---|:---|:---|\n"
        
        # 데이터 행 추가 (너무 많으면 슬랙 API 제한이 걸릴 수 있으므로 상위 30개 권장)
        for _, row in df.head(30).iterrows():
            # 제목이 너무 길 경우 가독성을 위해 줄임 처리
            short_title = row['title'][:25] + ".." if len(row['title']) > 25 else row['title']
            
            markdown_text += (
                f"| {row['company']} "
                f"| {short_title} "
                f"| {row['experience']} "
                f"| {row['first_seen']} "
                f"| [🔗]({row['link']}) |\n"
            )
            
        markdown_text += f"\n\n---\n*마지막 동기화 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*"

        # 4. 슬랙 API 호출 (성공했던 구조 유지)
        response = client.canvases_edit(
            canvas_id=CANVAS_ID,
            changes=[
                {
                    "operation": "replace",
                    "document_content": {
                        "type": "markdown",
                        "markdown": markdown_text
                    }
                }
            ]
        )
        
        if response["ok"]:
            print(f"✅ 슬랙 캔버스 업데이트 성공! (파일명: {CSV_PATH})")
        else:
            print(f"❌ 슬랙 API 응답 에러: {response['error']}")

    except Exception as e:
        print(f"❌ 실행 중 오류 발생: {e}")

if __name__ == "__main__":
    update_slack_canvas()
