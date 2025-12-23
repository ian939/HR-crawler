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
    'Referer': 'https://www.saramin.co.kr/'
}

def fetch_detail_content(url):
    """상세 본문 추출: 텍스트 우선 수집, 없으면 이미지 URL 수집"""
    try:
        time.sleep(2)
        target_url = url
        
        # [사람인 우회] 상세 요강 전용 URL로 변환
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

        # 본문 영역 탐색
        selectors = ['.user_content', '.recruit_view_cont', '.view_con', '.job_detail', '.template_area']
        content_area = None
        for sel in selectors:
            content_area = soup.select_one(sel)
            if content_area: break
        
        if not content_area:
            content_area = soup.body

        # 1. 텍스트 추출
        text_content = content_area.get_text(separator="\n", strip=True) if content_area else ""
        
        # 2. '채용공고 상세' 같은 노이즈 문구만 있거나 너무 짧으면 이미지 검색 (플러그링크 케이스)
        noise_text = ["채용공고 상세", "본문 내용을 찾을 수 없습니다", "로그인"]
        is_poor = len(text_content) < 150 or any(text_content.strip() == k for k in noise_text)

        if is_poor and content_area:
            imgs = content_area.find_all('img')
            img_urls = []
            for img in imgs:
                src = img.get('src') or img.get('data-src')
                if src:
                    if src.startswith('//'): src = "https:" + src
                    # 무관한 아이콘 이미지 필터링 (보통 공고 이미지는 크기가 큼)
                    if "icon" not in src.lower() and "logo" not in src.lower():
                        img_urls.append(src)
            
            if img_urls:
                return "[이미지 공고] " + ", ".join(img_urls)

        # 텍스트가 정상적이면 텍스트 반환
        if len(text_content) > 100:
            return text_content[:20000]
        
        return "상세 내용은 링크를 참조해 주세요."

    except Exception as e:
        return f"수집 실패: {str(e)}"

def get_bep_jobs():
    """BEP(워터) 전기차충전사업부문 수집 전용"""
    url = "https://bep.co.kr/Career/recruitment?type=3"
    jobs = []
    try:
        response = requests.get(url, headers=HEADERS)
        response.encoding = 'utf-8'
        soup = BeautifulSoup(response.text, 'html.parser')
        links = soup.find_all('a', href=re.compile(r'recruitmentView\?idx='))
        for l in links:
            title_text = l.get_text(" ", strip=True)
            if not title_text or "목록" in title_text: continue
            href = l.get('href', '')
            full_link = f"https://bep.co.kr{href}" if not href.startswith('http') else href
            clean_title = title_text.replace("모집중", "").strip()
            jobs.append(['BEP(워터)', clean_title, "공고 참조", full_link])
    except: pass
    return jobs

def get_saramin_jobs(companies):
    """사람인 기업 검색 수집"""
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
                    # 경력 정보 추출
                    conds = item.select('.job_condition span')
                    exp = conds[1].text.strip() if len(conds) > 1 else "상세 참조"
                    link = "https://www.saramin.co.kr" + title_tag['href']
                    jobs.append([co_name, title_tag.text.strip(), exp, link])
            time.sleep(1.5)
        except: continue
    return jobs

def safe_load_df(file_path, default_cols):
    """컬럼명 깨짐 방지 및 로드 안전장치"""
    if os.path.exists(file_path):
        try:
            df = pd.read_csv(file_path, encoding='utf-8-sig')
            df.columns = [c.strip().replace('\ufeff', '') for c in df.columns]
            for col in default_cols:
                if col not in df.columns: df[col] = ""
            return df[default_cols]
        except:
            return pd.DataFrame(columns=default_cols)
    return pd.DataFrame(columns=default_cols)

def main():
    saramin_targets = ["대영채비", "이브이시스", "플러그링크", "볼트업", "차지비", "에버온"]
    today = datetime.now().strftime('%Y-%m-%d')
    
    # 데이터 로드
    df_master = safe_load_df("job_listings_all.csv", ['company', 'title', 'experience', 'link', 'first_seen'])
    df_ency = safe_load_df("encyclopedia.csv", ['link', 'company', 'title', 'content', 'last_updated'])
    df_comp = safe_load_df("Recruitment_completed.csv", ['company', 'title', 'experience', 'link', 'completed_date'])

    print(f"[{today}] 수집 시작...")
    scraped = get_bep_jobs() + get_saramin_jobs(saramin_targets)
    df_current = pd.DataFrame(scraped, columns=['company', 'title', 'experience', 'link'])

    if df_current.empty: return

    # 1. 신규 공고 및 슬랙
    new_entries = df_current[~df_current['link'].isin(df_master['link'])].copy()
    if not new_entries.empty:
        new_entries['first_seen'] = today
        if SLACK_WEBHOOK_URL:
            msg = f"📢 *신규 채용 ({len(new_entries)}건)*\n"
            for _, r in new_entries.iterrows(): msg += f"• [{r['company']}] {r['title']} ({r['experience']})\n  <{r['link']}|보기>\n"
            requests.post(SLACK_WEBHOOK_URL, json={"text": msg})
        df_master = pd.concat([df_master, new_entries], ignore_index=True)

    # 2. 채용 종료 처리
    active_cos = df_current['company'].unique()
    is_missing = ~df_master['link'].isin(df_current['link'])
    is_safe = df_master['company'].isin(active_cos)
    closed = df_master[is_missing & is_safe].copy()
    if not closed.empty:
        closed['completed_date'] = today
        df_comp = pd.concat([df_comp, closed], ignore_index=True)
        df_master = df_master[~(is_missing & is_safe)]

    # 3. Encyclopedia (상세 내용) 업데이트
    # 내용이 부실한 것들 재수집 대상으로 포함
    bad_list = ["채용공고 상세", "본문 내용을 찾을 수 없습니다", "로그인", "링크 참조"]
    is_bad = df_ency['content'].apply(lambda x: any(k in str(x) for k in bad_list) or len(str(x)) < 150)
    
    target_links = list(set(df_ency[is_bad]['link'].tolist() + df_current[~df_current['link'].isin(df_ency['link'])]['link'].tolist()))

    if target_links:
        print(f"상세 본문/이미지 {len(target_links)}건 작업 중...")
        for link in target_links:
            source = df_current[df_current['link'] == link]
            if source.empty: source = df_master[df_master['link'] == link]
            if source.empty: continue
            
            row = source.iloc[0]
            content = fetch_detail_content(link)
            
            if link in df_ency['link'].values:
                df_ency.loc[df_ency['link'] == link, ['content', 'last_updated']] = [content, today]
            else:
                new_row = pd.DataFrame([{'link': link, 'company': row['company'], 'title': row['title'], 'content': content, 'last_updated': today}])
                df_ency = pd.concat([df_ency, new_row], ignore_index=True)

    # 파일 저장
    df_master.to_csv("job_listings_all.csv", index=False, encoding='utf-8-sig')
    df_comp.to_csv("Recruitment_completed.csv", index=False, encoding='utf-8-sig')
    df_ency.to_csv("encyclopedia.csv", index=False, encoding='utf-8-sig')
    print("수집 완료.")

if __name__ == "__main__":
    main()
