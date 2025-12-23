import time
import random
import re
from datetime import datetime
import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

def get_driver():
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    driver.set_page_load_timeout(30)
    return driver

def format_experience(text):
    """'경력 3년↑', '신입', '경력무관' 등으로 텍스트를 정제하는 함수"""
    if not text: return "경력무관"
    
    # 1. 숫자+년 형태 찾기 (ex: 5년, 3~5년)
    match = re.search(r'(\d+)년', text)
    if match:
        return f"경력{match.group(1)}↑"
    
    # 2. '신입' 단어 포함 여부
    if "신입" in text and "경력" in text:
        return "신입·경력"
    if "신입" in text:
        return "신입"
    
    # 3. 그 외 무관 처리
    if "무관" in text:
        return "경력무관"
        
    return "경력확인필요"

def crawl_bep_official(driver):
    """'워터' 공식홈페이지 - 경력 정보 포함 수집"""
    print(">>> [워터] 공식홈페이지 수집 중...")
    url = "https://bep.co.kr/Career/recruitment?type=3"
    results = []
    try:
        driver.get(url)
        time.sleep(7)
        items = driver.find_elements(By.CSS_SELECTOR, "div, p, span, li")
        for item in items:
            text = item.text.strip()
            # 공고 제목 패턴 (매니저, 엔지니어 등) 검색
            if any(k in text for k in ['매니저', '엔지니어', '담당', '팀장', '채용', '모집']):
                if 5 < len(text) < 60:
                    # BEP는 제목 안에 경력이 포함된 경우가 많으므로 제목에서 추출 시도
                    exp = format_experience(text)
                    results.append({
                        'site': '공식홈',
                        'company': '워터(BEP)',
                        'title': text,
                        'experience': exp,
                        'link': url
                    })
    except Exception as e:
        print(f"  - BEP 오류: {e}")
    return results

def crawl_all():
    companies = ["대영채비", "이브이시스", "플러그링크", "볼트업", "차지비", "에버온"]
    results = []
    driver = get_driver()

    # 1. 워터 공식홈
    results.extend(crawl_bep_official(driver))

    for company in companies:
        print(f"\n>>> [{company}] 수집 시작")
        
        # [사람인] - .job_condition 영역에서 경력 추출
        try:
            driver.get(f"https://www.saramin.co.kr/zf_user/search/recruit?searchword={company}")
            time.sleep(3)
            items = driver.find_elements(By.CSS_SELECTOR, ".item_recruit")
            for item in items[:10]:
                corp = item.find_element(By.CSS_SELECTOR, ".corp_name").text.strip()
                if company in corp:
                    title = item.find_element(By.CSS_SELECTOR, ".job_tit").text.strip()
                    # 경력 정보가 담긴 조건 영역
                    cond_text = item.find_element(By.CSS_SELECTOR, ".job_condition").text
                    results.append({
                        'site': '사람인', 'company': corp, 'title': title,
                        'experience': format_experience(cond_text),
                        'link': item.find_element(By.CSS_SELECTOR, ".job_tit a").get_attribute('href')
                    })
        except: pass

        # [원티드] - 카드 내 태그나 메타 정보 활용
        try:
            driver.get(f"https://www.wanted.co.kr/search?query={company}&tab=position")
            time.sleep(5)
            items = driver.find_elements(By.CSS_SELECTOR, '[data-cy="post-card"]')
            for item in items[:10]:
                corp = item.find_element(By.CSS_SELECTOR, '.job-card-company-name').text.strip()
                if company in corp:
                    title = item.find_element(By.CSS_SELECTOR, '.job-card-title').text.strip()
                    # 원티드 리스트는 경력이 제목 아래 작게 표시됨
                    try:
                        meta = item.text # 카드 전체 텍스트에서 경력 패턴 검색
                        exp = format_experience(meta)
                    except: exp = "경력확인필요"
                    
                    results.append({
                        'site': '원티드', 'company': corp, 'title': title,
                        'experience': exp,
                        'link': item.find_element(By.TAG_NAME, 'a').get_attribute('href')
                    })
        except: pass

        # [잡코리아] - .etc 혹은 .option 영역
        try:
            driver.get(f"https://www.jobkorea.co.kr/Search/?stext={company}")
            time.sleep(5)
            items = driver.find_elements(By.CSS_SELECTOR, ".list-post .post")
            for item in items[:10]:
                corp = item.find_element(By.CSS_SELECTOR, ".name").text.strip()
                if company in corp:
                    title = item.find_element(By.CSS_SELECTOR, ".title").text.strip()
                    # 잡코리아는 .exp 또는 .option 클래스에 경력 표시
                    exp_text = item.find_element(By.CSS_SELECTOR, ".exp, .option, .etc").text
                    results.append({
                        'site': '잡코리아', 'company': corp, 'title': title,
                        'experience': format_experience(exp_text),
                        'link': item.find_element(By.CSS_SELECTOR, "a.title").get_attribute('href')
                    })
        except: pass

    driver.quit()

    if results:
        df = pd.DataFrame(results).drop_duplicates(subset=['company', 'title'])
        # 날짜별 파일명 생성 (예: jobs_20251223.csv)
        today_date = datetime.now().strftime('%Y%m%d')
        filename = f"jobs_{today_date}.csv"
        
        df.to_csv(filename, index=False, encoding='utf-8-sig')
        print(f"\n✅ 수집 완료: {filename} 저장됨 (총 {len(df)}건)")
    else:
        print("\n❌ 수집된 데이터가 없습니다.")

if __name__ == "__main__":
    crawl_all()
