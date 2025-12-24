import requests
from bs4 import BeautifulSoup
import pandas as pd
from datetime import datetime
import time
import re
import os
from urllib.parse import urljoin

# --- 환경 설정 ---
SLACK_WEBHOOK_URL = os.environ.get('SLACK_WEBHOOK_URL')
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
    'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7',
    'Connection': 'keep-alive'
}

def safe_load_df(file_path, default_cols):
    """파일 로드 시 컬럼명을 강제하고 중복 제거"""
    if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
        try:
            df = pd.read_csv(file_path, encoding='utf-8-sig')
            df.columns = [c.strip().replace('\ufeff', '') for c in df.columns]
            # 필요한 컬럼이 없으면 생성
            for col in default_cols:
                if col not in df.columns:
                    df[col] = ""
            return df[default_cols].drop_duplicates(subset=['link'])
        except Exception as e:
            print(f"로드 실패({file_path}): {e}")
            return pd.DataFrame(columns=default_cols)
    return pd.DataFrame(columns=default_cols)

def fetch_detail_content(url):
    """상세 본문 추출 (이미지 포함)"""
    try:
        time.sleep(1)
        target_url = url
        if "saramin.co.kr" in url and "rec_idx=" in url:
            rec_idx_match = re.search(r'rec_idx=(\d+)', url)
            if rec_idx_match:
                target_url = f"https://www.saramin.co.kr/zf_user/jobs/relay/view-detail?rec_idx={rec_idx_match.group(1)}"

        res = requests.get(target_url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(res.text, 'html.parser')
        
        for tag in soup(["script", "style", "nav", "footer", "header", "button"]):
            tag.decompose()

        content_area = soup.select_one('.user_content, .recruit_view_cont, .view_con, body')
        text_content = content_area.get_text(separator="\n", strip=True) if content_area else ""
        
        # 내용이 부실하면 이미지 추출
        if len(text_content) < 150 and content_area:
            imgs = content_area.find_all('img')
            img_urls = [urljoin(url, i.get('src') or i.get('data-src')) for i in imgs if i.get('src') or i.get('data-src')]
            clean_imgs = [i for i in img_urls if not any(x in i.lower() for x in ["icon", "logo", "common"])]
            if clean_imgs: return "[이미지 공고] " + ", ".join(clean_imgs)

        return text_content[:15000] if len(text_content) > 50 else "상세 링크 참조"
    except:
        return "수집 실패"

def get_bep_jobs():
    """BEP(워터) 수집 보완 - Session 사용 및 정밀 매칭"""
    url = "https://bep.co.kr/Career/recruitment?type=3"
    jobs = []
    try:
        with requests.Session() as s:
            s.headers.update(HEADERS)
            res = s.get(url, timeout=15)
            soup = BeautifulSoup(res.text, 'html.parser')
            
            # BEP는 보통 table이나 div.list 내에 a 태그가 존재
            links = soup.find_all('a', href=re.compile(r'recruitmentView\?idx='))
            for l in links:
                title = l.get_text(" ", strip=True).replace("모집중", "").strip()
                if not title or "목록" in title: continue
                
                href = l.get('href')
                full_link = urljoin("https://bep.co.kr", href)
                jobs.append(['BEP(워터)', title, "공고 확인", full_link])
    except Exception as e:
        print(f"BEP 수집 오류: {e}")
    return jobs

def get_saramin_jobs(companies):
    """사람인 수집"""
    base_url = "https://www.saramin.co.kr/zf_user/search/recruit"
    jobs = []
    for company in companies:
        try:
            params = {'searchword': company, 'searchType': 'search'}
            res = requests.get(base_url, headers=HEADERS, params=params, timeout=15)
            soup = BeautifulSoup(res.text, 'html.parser')
            for item in soup.select('.item_recruit'):
                co_tag = item.select_one('.corp_name a')
                if co_tag and company in co_tag.text:
                    title_tag = item.select_one('.job_tit a')
                    conds = item.select('.job_condition span')
                    exp = conds[1].text.strip() if len(conds) > 1 else "경력무관"
                    jobs.append([co_tag.text.strip(), title_tag.text.strip(), exp, "https://www.saramin.co.kr" + title_tag['href']])
            time.sleep(1)
        except: continue
    return jobs

def main():
    today = datetime.now().strftime('%Y-%m-%d')
    
    # 1. 데이터 로드 (컬럼 보장)
    df_master = safe_load_df("job_listings_all.csv", ['company', 'title', 'experience', 'link', 'first_seen'])
    df_ency = safe_load_df("encyclopedia.csv", ['link', 'company', 'title', 'content', 'last_updated'])
    df_comp = safe_load_df("Recruitment_completed.csv", ['company', 'title', 'experience', 'link', 'completed_date'])

    print(f"[{today}] 수집 시작...")
    scraped = get_bep_jobs() + get_saramin_jobs(["대영채비", "이브이시스", "플러그링크", "볼트업", "차지비", "에버온"])
    df_current = pd.DataFrame(scraped, columns=['company', 'title', 'experience', 'link']).drop_duplicates(subset=['link'])

    if df_current.empty:
        print("수집된 공고가 없습니다.")
        return

    # 2. 신규 알림 및 병합 (중복 원천 차단)
    new_entries = df_current[~df_current['link'].isin(df_master['link'])].copy()
    if not new_entries.empty:
        new_entries['first_seen'] = today
        if SLACK_WEBHOOK_URL:
            msg = f"📢 *신규 채용 ({len(new_entries)}건)*\n"
            for _, r in new_entries.iterrows():
                msg += f"• [{r['company']}] {r['title']}\n  <{r['link']}|보기>\n"
            requests.post(SLACK_WEBHOOK_URL, json={"text": msg})
        df_master = pd.concat([df_master, new_entries], ignore_index=True)

    # 3. 채용 종료 처리
    active_links = df_current['link'].tolist()
    is_closed = (~df_master['link'].isin(active_links)) & (df_master['company'].isin(df_current['company'].unique()))
    closed_jobs = df_master[is_closed].copy()
    if not closed_jobs.empty:
        closed_jobs['completed_date'] = today
        df_comp = pd.concat([df_comp, closed_jobs], ignore_index=True).drop_duplicates(subset=['link'])
        df_master = df_master[~is_closed]

    # 4. Encyclopedia 업데이트 (KeyError 방어 로직)
    # df_ency에 link 컬럼이 확실히 있는지 확인
    if 'link' in df_ency.columns:
        retry_keywords = ["수집 실패", "로그인", "상세 링크 참조"]
        is_bad = df_ency['content'].apply(lambda x: any(k in str(x) for k in retry_keywords) or len(str(x)) < 150)
        
        # 기존 부실 데이터 링크 + 신규 데이터 중 미등록 링크
        target_links = df_ency[is_bad]['link'].tolist() + df_master[~df_master['link'].isin(df_ency['link'])]['link'].tolist()
        target_links = list(set(target_links))

        if target_links:
            print(f"상세 수집 중... ({len(target_links)}건)")
            for link in target_links:
                info = df_master[df_master['link'] == link]
                if info.empty: continue
                
                content = fetch_detail_content(link)
                if link in df_ency['link'].values:
                    df_ency.loc[df_ency['link'] == link, ['content', 'last_updated']] = [content, today]
                else:
                    new_row = pd.DataFrame([{'link': link, 'company': info.iloc[0]['company'], 'title': info.iloc[0]['title'], 'content': content, 'last_updated': today}])
                    df_ency = pd.concat([df_ency, new_row], ignore_index=True)

    # 5. 저장
    df_master.to_csv("job_listings_all.csv", index=False, encoding='utf-8-sig')
    df_comp.to_csv("Recruitment_completed.csv", index=False, encoding='utf-8-sig')
    df_ency.to_csv("encyclopedia.csv", index=False, encoding='utf-8-sig')
    print(f"작업 완료. (현재 공고: {len(df_master)}건)")

if __name__ == "__main__":
    main()
