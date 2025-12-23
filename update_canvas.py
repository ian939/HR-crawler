import os
import pandas as pd
from slack_sdk import WebClient
from datetime import datetime

# 1. 설정 (이 부분의 파일명을 꼭 확인하세요!)
SLACK_TOKEN = os.environ.get("SLACK_BOT_TOKEN")
CANVAS_ID = os.environ.get("SLACK_CANVAS_ID")
CSV_FILENAME = "job_listings_all.csv" # 리포지토리에 저장된 실제 파일명

GITHUB_USER = "ian939"
GITHUB_REPO = "HR-crawler"

# 다운로드 링크: raw 대신 blob을 사용하여 GitHub UI를 통해 안전하게 받도록 설정
DOWNLOAD_URL = f"https://github.com/{GITHUB_USER}/{GITHUB_REPO}/blob/main/{CSV_FILENAME}"

def update_slack_canvas():
    if not SLACK_TOKEN or not CANVAS_ID:
        print("❌ 설정 오류: 토큰 또는 캔버스 ID가 없습니다.")
        return

    client = WebClient(token=SLACK_TOKEN)

    try:
        # 2. 파일 존재 여부 및 데이터 유효성 검사
        if not os.path.exists(CSV_FILENAME):
            print(f"❌ 파일 없음: {CSV_FILENAME}을 찾을 수 없습니다.")
            return
            
        df = pd.read_csv(CSV_FILENAME)
        
        # 데이터가 너무 적거나 없을 경우 업데이트 중단 (증발 방지)
        if len(df) < 1:
            print("⚠️ 데이터가 0개입니다. 캔버스를 보호하기 위해 업데이트를 건너뜁니다.")
            return

        # 3. 마크다운 생성
        today = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # 가독성을 위해 상단 문구 수정
        markdown_text = f"# 🚀 채용 공고 리포트 ({today.split()[0]})\n\n"
        markdown_text += "### 📥 데이터 다운로드 및 확인\n"
        markdown_text += f"> [**💾 전체 CSV 데이터 다운로드 (GitHub)**]({DOWNLOAD_URL})\n"
        markdown_text += f"*마지막 업데이트 시각: {today}*\n\n---\n\n"
        
        # 표 헤더 (강제 너비 확장 적용)
        markdown_text += "| 회사명 | 공고 제목" + "　" * 20 + " | 경력 | 등록일 | 🔗 |\n"
        markdown_text += "|:---|:---|:---|:---|:---:|\n"
        
        # 데이터가 너무 많으면 API 오류가 날 수 있으므로 30개로 제한
        sample_df = df.sort_values(by='first_seen', ascending=False).head(30)
        
        for _, row in sample_df.iterrows():
            # 데이터 내 특수문자로 인한 깨짐 방지
            title = str(row['title']).replace('|', '｜').strip()
            if len(title) > 40: title = title[:40] + ".."
            
            markdown_text += (
                f"| {row['company']} "
                f"| {title} "
                f"| {row['experience']} "
                f"| {row['first_seen']} "
                f"| [🔗]({row['link']}) |\n"
            )

        # 4. 슬랙 API 호출
        response = client.canvases_edit(
            canvas_id=CANVAS_ID,
            changes=[{
                "operation": "replace",
                "document_content": {
                    "type": "markdown",
                    "markdown": markdown_text
                }
            }]
        )
        
        if response["ok"]:
            print(f"✅ 업데이트 성공! (데이터 {len(sample_df)}개 반영)")
        else:
            print(f"❌ API 오류: {response['error']}")

    except Exception as e:
        print(f"❌ 실행 중 오류 발생: {e}")

if __name__ == "__main__":
    update_slack_canvas()
