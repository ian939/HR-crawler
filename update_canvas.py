import os
import pandas as pd
from slack_sdk import WebClient
from datetime import datetime

# 1. 환경 변수 설정 (로컬 테스트 시에는 직접 입력, GitHub에서는 Secrets 사용)
SLACK_TOKEN = os.environ.get("SLACK_BOT_TOKEN")
CANVAS_ID = os.environ.get("SLACK_CANVAS_ID")
CSV_FILE = "encyclopedia.csv" # 실제 파일명에 맞게 수정하세요

def update_canvas():
    if not SLACK_TOKEN or not CANVAS_ID:
        print("❌ 설정 오류: 토큰 또는 캔버스 ID가 없습니다.")
        return

    client = WebClient(token=SLACK_TOKEN)
    
    try:
        # 2. CSV 데이터 로드 및 마크다운 변환
        df = pd.read_csv(CSV_FILE)
        today = datetime.now().strftime('%Y-%m-%d')
        
        markdown = f"# 🚀 채용 정보 자동 업데이트 ({today})\n\n"
        markdown += f"현재 **총 {len(df)}개**의 공고가 올라와 있습니다.\n\n---\n"
        
        # 요약 테이블 생성
        markdown += "### 📊 공고 요약\n| 회사명 | 공고 제목 | 링크 |\n|:---|:---|:---|\n"
        for _, row in df.head(15).iterrows(): # 상위 15개만 요약
            title = row['title'][:30] + "..." if len(row['title']) > 30 else row['title']
            markdown += f"| {row['company']} | {title} | [🔗]({row['link']}) |\n"
        
        markdown += f"\n\n---\n*마지막 업데이트: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*"

        # 3. 캔버스 전송 (성공했던 API 규격 적용)
        response = client.canvases_edit(
            canvas_id=CANVAS_ID,
            changes=[
                {
                    "operation": "replace",
                    "document_content": {
                        "type": "markdown",
                        "markdown": markdown
                    }
                }
            ]
        )
        
        if response["ok"]:
            print(f"✅ {today} 캔버스 업데이트 완료!")
            
    except Exception as e:
        print(f"❌ 오류 발생: {e}")

if __name__ == "__main__":
    update_canvas()
