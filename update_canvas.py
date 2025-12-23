import os
import pandas as pd
from slack_sdk import WebClient
from datetime import datetime

# 1. 환경 변수에서 설정값 로드 (GitHub Secrets와 연결됨)
SLACK_TOKEN = os.environ.get("SLACK_BOT_TOKEN")
CANVAS_ID = os.environ.get("SLACK_CANVAS_ID")
CSV_PATH = "encyclopedia.csv" # 크롤러가 생성하는 파일명에 맞게 확인 필요

def update_slack_canvas():
    if not SLACK_TOKEN or not CANVAS_ID:
        print("❌ 에러: SLACK_BOT_TOKEN 또는 SLACK_CANVAS_ID가 설정되지 않았습니다.")
        return

    client = WebClient(token=SLACK_TOKEN)

    try:
        # 2. CSV 파일 읽기
        if not os.path.exists(CSV_PATH):
            print(f"❌ 에러: {CSV_PATH} 파일을 찾을 수 없습니다.")
            return
            
        df = pd.read_csv(CSV_PATH)
        today = datetime.now().strftime('%Y-%m-%d')
        
        # 3. 캔버스용 마크다운 생성
        markdown_text = f"# 🚀 채용 정보 데일리 업데이트 ({today})\n\n"
        markdown_text += f"오늘 확인된 공고는 총 **{len(df)}개**입니다.\n\n---\n\n"
        
        # 요약 테이블 (최신 15개)
        markdown_text += "### 📊 채용 공고 요약\n| 회사명 | 공고 제목 | 링크 |\n|:---|:---|:---|\n"
        for _, row in df.head(15).iterrows():
            title = row['title'][:30] + "..." if len(row['title']) > 30 else row['title']
            markdown_text += f"| {row['company']} | {title} | [👉 바로가기]({row['link']}) |\n"
            
        markdown_text += f"\n\n---\n*마지막 자동 업데이트 시각: {datetime.now().strftime('%H:%M:%S')}*"

        # 4. 슬랙 API 호출 (테스트 성공했던 그 구조!)
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
            print(f"✅ 슬랙 캔버스 업데이트 성공! ({today})")
        else:
            print(f"❌ 슬랙 API 응답 에러: {response['error']}")

    except Exception as e:
        print(f"❌ 실행 중 오류 발생: {e}")

if __name__ == "__main__":
    update_slack_canvas()
