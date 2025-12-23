import requests
from bs4 import BeautifulSoup
import pandas as pd
from datetime import datetime
import time
import re
import os

# --- 환경 설정 ---
SLACK_WEBHOOK_URL = os.environ.get('SLACK_WEBHOOK_URL')
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
}

def fetch_detail_content(url):
    """상세 페이지 본문 추출 (사람인 우회 및 노이즈 제거)"""
    try:
        time.sleep(2)
        target_url = url
        # 사람인은 상세내용이 별도 URL(view-detail)에 담겨있는 경우가 많음 (로그인 창 회피용)
        if "saramin.co.kr" in url and "rec_idx=" in url:
            rec_idx_match = re.search(r'rec_idx=(\d+)', url)
            if rec_idx_match:
                target_url = f"https://www.saramin.co.kr/zf_user/jobs/relay/view-detail?rec_idx={rec_idx_match.group(1)}"

        res = requests.get(target_url, headers=HEADERS, timeout=15)
        res.encoding = 'utf-8'
        soup = BeautifulSoup(res.text, 'html.parser')

        # 불필요한 요소 제거
        for tag in soup(["script", "style", "nav", "footer", "header", "button", "aside"]):
            tag.decompose()

        # 주요 본문 선택자
        selectors = ['.user_content', '.recruit_view_cont', '.view_con', '.job_detail', '.template_area']
        content_text = ""
        for sel in selectors:
            target = soup.select_one(sel)
            if target:
                content_text = target.get_text(separator="\n", strip=True)
                break
        
        if not content_text or len(content_text) < 100:
            content_text = soup.get_text(separator="\n", strip=True)

        # 로그인 유도 문구가 본문의 절반 이상이면 수집 실패로 간주
        if "로그인" in content_text[:200] and len(content_text) < 500:
            return "본문 내용 확인 불가 (링크 참조)"

        return content_text[:15000] # CSV 저장 한계 고려
    except Exception as e:
        return f"수집 실패: {str(e)}"

def get_bep_jobs():
    """BEP 수집 로직 - 키워드 필터링 강화"""
    url = "https://bep.co.kr/Career/recruitment"
    jobs = []
    try:
        response = requests.get(url, headers=HEADERS)
        response.encoding = 'utf-8'
        soup = BeautifulSoup(response.text, 'html.parser')
        links = soup.find_all('a', href=re.compile(r'recruitmentView\?idx='))
        for l in links:
            text = l.get_text(" ", strip=True)
            if any(k in text for k in ["전기차", "충전", "워터", "WATER", "운영", "모집중"]):
                href = l.get('href', '')
                full_link = f"https://bep.co.kr{href}" if not href.startswith('http') else href
                title = text.replace("모집중", "").strip()
                jobs.append(['BEP', title, "공고 참조", full_link])
    except: pass
    return jobs

def get_saramin_jobs(companies):
    base_url = "https://www.saramin.co.kr/zf_user/search/recruit"
    jobs = []
    for company in companies:
        try:
            params = {'searchword': company, 'searchType': 'search'}
            res = requests.get(base_url, headers=HEADERS, params=params)
            soup = BeautifulSoup(res.text, 'html.parser')
            items = soup.select('.item_recruit')
            for item in items:
                co_tag = item.select_one('.corp_name a')
                if not co_tag: continue
                co_name = co_tag.text.strip()
                if company in co_name.replace("(주)", "").replace("주식회사", ""):
                    title_tag = item.select_one('.job_tit a')
                    jobs.append([co_name, title_tag.text.strip(), "공고 참조", "https://www.saramin.co.kr" + title_tag['href']])
            time.sleep(1.5)
        except: continue
    return jobs

def safe_load_df(file_path, default_cols):
    """[KeyError 해결] 파일 로드 시 컬럼명을 표준화하여 읽어옴"""
    if os.path.exists(file_path):
        try:
            df = pd.read_csv(file_path, encoding='utf-8-sig')
            # 컬럼명에 붙은 BOM(\ufeff) 및 앞뒤 공백 제거
            df.columns = [c.strip().replace('\ufeff', '') for c in df.columns]
            # 필수 컬럼이 없으면 빈 컬럼 생성
            for col in default_cols:
                if col not in df.columns:
                    df[col] = ""
            return df
        except:
            return pd.DataFrame(columns=default_cols)
    return pd.DataFrame(columns=default_cols)

def main():
    target_companies = ["대영채비", "이브이시스", "플러그링크", "볼트업", "차지비", "에버온"]
    today = datetime.now().strftime('%Y-%m-%d')
    
    # 데이터 로드 (안전 로직 적용)
    df_master = safe_load_df("job_listings_all.csv", ['company', 'title', 'experience', 'link', 'first_seen'])
    df_ency = safe_load_df("encyclopedia.csv", ['link', 'company', 'title', 'content', 'last_updated'])
    df_comp = safe_load_df("Recruitment_completed.csv", ['company', 'title', 'experience', 'link', 'completed_date'])

    print("데이터 수집 시작...")
    scraped = get_bep_jobs() + get_saramin_jobs(target_companies)
    df_current = pd.DataFrame(scraped, columns=['company', 'title', 'experience', 'link'])

    if df_current.empty:
        print("수집된 데이터가 없습니다. 종료합니다.")
        return

    # 1. 신규 공고 처리 및 슬랙
    new_entries = df_current[~df_current['link'].isin(df_master['link'])].copy()
    if not new_entries.empty:
        new_entries['first_seen'] = today
        if SLACK_WEBHOOK_URL:
            msg = f"📢 *신규 채용 ({len(new_entries)}건)*\n"
            for _, r in new_entries.iterrows(): msg += f"• [{r['company']}] {r['title']}\n  <{r['link']}|보기>\n"
            requests.post(SLACK_WEBHOOK_URL, json={"text": msg})
        df_master = pd.concat([df_master, new_entries], ignore_index=True)

    # 2. 채용 종료 처리 (수집 성공한 회사 대상)
    scanned_cos = df_current['company'].unique()
    is_missing = ~df_master['link'].isin(df_current['link'])
    is_safe = df_master['company'].isin(scanned_cos)
    
    closed_entries = df_master[is_missing & is_safe].copy()
    if not closed_entries.empty:
        closed_entries['completed_date'] = today
        df_comp = pd.concat([df_comp, closed_entries], ignore_index=True)
        df_master = df_master[~(is_missing & is_safe)]

    # 3. Encyclopedia 업데이트 (KeyError 방지 적용)
    # 내용이 부실하거나 없는 항목 필터링
    bad_contents = ["본문 내용을 찾을 수 없습니다", "로그인", "수집 실패", "확인 불가", "링크 참조"]
    is_bad = df_ency['content'].apply(lambda x: any(k in str(x) for k in bad_contents) or pd.isna(x))
    
    retry_links = df_ency[is_bad]['link'].tolist()
    add_links = df_current[~df_current['link'].isin(df_ency['link'])]['link'].tolist()
    target_links = list(set(retry_links + add_links))

    if target_links:
        print(f"상세 내용 {len(target_links)}건 수집/업데이트 중...")
        for link in target_links:
            # 기본 정보 매칭
            info = df_current[df_current['link'] == link]
            if info.empty: info = df_master[df_master['link'] == link]
            if info.empty: continue
            
            row = info.iloc[0]
            content = fetch_detail_content(link)
            
            if link in df_ency['link'].values:
                df_ency.loc[df_ency['link'] == link, ['content', 'last_updated']] = [content, today]
            else:
                new_row = pd.DataFrame([{'link': link, 'company': row['company'], 'title': row['title'], 'content': content, 'last_updated': today}])
                df_ency = pd.concat([df_ency, new_row], ignore_index=True)

    # 4. 파일 저장
    df_master.to_csv("job_listings_all.csv", index=False, encoding='utf-8-sig')
    df_comp.to_csv("Recruitment_completed.csv", index=False, encoding='utf-8-sig')
    df_ency.to_csv("encyclopedia.csv", index=False, encoding='utf-8-sig')
    print(f"[{today}] 모든 데이터 저장 완료.")

if __name__ == "__main__":
    main()
