import time
import re
import random
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
    driver.set_page_load_timeout(60) # 페이지 로딩 대기 시간 충분히 확보
    return driver

def extract_exp(text):
    """텍스트에서 경력 정보를 추출하는 강화된 함수"""
    if not text: return ""
    
    # 1. 'N년', 'N~M년' 형태 (숫자 추출 우선)
    match = re.search(r'(\d+)\s*년', text)
    if match:
        return f"경력{match.group(1)}↑"
    
    # 2. '신입' 단어 포함 여부
    if "신입" in text:
        return "신입"
    
    # 3. '경력' 단어는 있으나 숫자가 없는 경우
    if "경력" in text:
        return "경력"
        
    return "" # 추출 실패 시 빈값(null) 유지

def crawl_bep_official(driver):
    """'워터' 공식홈페이지 전용 로직 - 선택자 및 대기 보강"""
    print(">>> [워터] 공식홈페이지 수집 중...")
    url = "https://bep.co.kr/Career/recruitment?type=3"
    results = []
    try:
        driver.get(url)
        # 페이지 로딩 및 자바스크립트 실행 완료 대기
        time.sleep(12) 
        
        # 워터 홈페이지의 공고 카드 리스트 타겟팅
        # 클래스명이 유동적일 수 있어 텍스트와 구조적 특징 활용
        containers = driver.find_elements(By.CSS_SELECTOR, "div[class*='item'], div[class*='card'], .recruitment-list > a")
        
        if not containers:
            # 선택자로 못 잡을 경우 텍스트 노드 탐색
            containers = driver.find_elements(By.XPATH, "//div[contains(., '모집중')]")

        for item in containers:
            try:
                raw_text = item.text.strip().replace('\n', ' ')
                if "모집중" in raw_text or any(k in raw_text for k in ['매니저', '엔지니어', '팀장']):
                    # 제목 추출 (보통 첫 줄이나 특정 키워드 앞)
                    title = raw_text.split('모집중')[0].strip() if '모집중' in raw_text else raw_text[:40]
                    results.append({
                        'site': '공식홈',
                        'company': '워터(BEP)',
                        'title': title,
                        'experience': extract_exp(raw_text),
                        'link': url
                    })
            except: continue
            
    except Exception as e:
        print(f"  - BEP 수집 중 오류: {e}")
    return results

def crawl_all():
    # 포털 검색 대상 (워터 제외)
    companies = ["대영채비", "이브이시스", "플러그링크", "볼트업", "차지비", "에버온"]
    results = []
    driver = get_driver()

    # 1. 워터 공식홈 수집
    results.extend(crawl_bep_official(driver))

    # 2. 포털 사이트 수집
    for company in companies:
        print(f"\n>>> [{company}] 수집 시작")
        
        # [사람인] - 경력 정보 필드 정밀 타겟팅
        try:
            driver.get(f"https://www.saramin.co.kr/zf_user/search/recruit?searchword={company}")
            time.sleep(4)
            items = driver.find_elements(By.CSS_SELECTOR, ".item_recruit")
            for item in items[:12]:
                corp = item.find_element(By.CSS_SELECTOR, ".corp_name").text.strip()
                if company in corp:
                    title = item.find_element(By.CSS_SELECTOR, ".job_tit").text.strip()
                    # 사람인 경력 정보는 .job_condition 안의 텍스트에 있음
                    condition = item.find_element(By.CSS_SELECTOR, ".job_condition").text
                    results.append({
                        'site': '사람인', 'company': corp, 'title': title,
                        'experience': extract_exp(condition),
                        'link': item.find_element(By.CSS_SELECTOR, ".job_tit a").get_attribute('href')
                    })
        except: pass

        # [원티드]
        try:
            driver.get(f"https://www.wanted.co.kr/search?query={company}&tab=position")
            time.sleep(6)
            cards = driver.find_elements(By.CSS_SELECTOR, '[data-cy="post-card"]')
            for card in cards[:12]:
                corp = card.find_element(By.CSS_SELECTOR, '.job-card-company-name').text.strip()
                if company in corp:
                    title = card.find_element(By.CSS_SELECTOR, '.job-card-title').text.strip()
                    results.append({
                        'site': '원티드', 'company': corp, 'title': title,
                        'experience': extract_exp(card.text),
                        'link': card.find_element(By.TAG_NAME, 'a').get_attribute('href')
                    })
        except: pass

        # [잡코리아]
        try:
            driver.get(f"https://www.jobkorea.co.kr/Search/?stext={company}")
            time.sleep(5)
            posts = driver.find_elements(By.CSS_SELECTOR, ".list-post .post")
            for post in posts[:12]:
                corp = post.find_element(By.CSS_SELECTOR, ".name").text.strip()
                if company in corp:
                    title = post.find_element(By.CSS_SELECTOR, ".title").text.strip()
                    # 잡코리아는 .exp 클래스 명시적으로 존재
                    try:
                        exp_text = post.find_element(By.CSS_SELECTOR, ".exp, .option").text
                    except: exp_text = post.text
                    results.append({
                        'site': '잡코리아', 'company': corp, 'title': title,
                        'experience': extract_exp(exp_text),
                        'link': post.find_element(By.CSS_SELECTOR, "a.title").get_attribute('href')
                    })
        except: pass

    driver.quit()

    if results:
        df = pd.DataFrame(results).drop_duplicates(subset=['company', 'title'])
        # 컬럼 순서 고정 및 빈 값 유지
        df = df[['site', 'company', 'title', 'experience', 'link']]
        
        # 파일명 날짜 반영
        filename = f"jobs_{datetime.now().strftime('%Y%m%d')}.csv"
        df.to_csv(filename, index=False, encoding='utf-8-sig')
        print(f"\n✅ 완료: {filename} 저장 ({len(df)}건)")
    else:
        print("\n❌ 데이터 수집 실패")

if __name__ == "__main__":
    crawl_all()
