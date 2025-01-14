import streamlit as st
import os
import time
import pandas as pd
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import logging
from datetime import datetime
from urllib.parse import quote, urljoin
import shutil

# 페이지 설정
st.set_page_config(page_title="입찰정보 수집기", page_icon="🔍", layout="wide")

# 로깅 설정
logging.basicConfig(
    filename="bid_scraper.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

# 기관 URL 정보
REGIONAL_OFFICES = {
    "대전청": "/drocm/USR/tender/m_16067/lst.jsp",
    "익산청": "/irocm/USR/tender/m_15646/lst.jsp",
    "부산청": "/brocm/USR/tender/m_15120/lst.jsp",
    "원주청": "/wrocm/USR/tender/m_15962/lst.jsp",
    "서울청": "/srocm/USR/tender/m_13081/lst.jsp",
}

RIVER_OFFICES = {
    "한강유역환경청": "/hepm/USR/tender/m_14626/lst.jsp",
    "낙동강유역환경청": "/nepm/USR/tender/m_14626/lst.jsp",
    "금강유역환경청": "/gepm/USR/tender/m_14626/lst.jsp",
    "영산강유역환경청": "/yepm/USR/tender/m_14626/lst.jsp",
    "원주지방환경청": "/wjepm/USR/tender/m_14626/lst.jsp",
    "대구지방환경청": "/wjepm/USR/tender/m_14626/lst.jsp",
    "전북지방환경청": "/wjepm/USR/tender/m_14626/lst.jsp",
    "수도권대기환경청": "/wjepm/USR/tender/m_14626/lst.jsp",
    "환경부": "/wjepm/USR/tender/m_14626/lst.jsp",
}


def fix_detail_url(url, base_org):
    """상세 페이지 URL 수정"""
    if not url:
        return None

    try:
        base_paths = {
            **{k: v.replace("/lst.jsp", "") for k, v in REGIONAL_OFFICES.items()},
            **{k: v.replace("/lst.jsp", "") for k, v in RIVER_OFFICES.items()},
        }
        base_url = "https://www.molit.go.kr"

        if "mng.jsp" in url:
            params_start = url.find("mng.jsp") + 7
            params = url[params_start:]
            encoded_params = "&".join(
                f"{k}={quote(v)}" if v else f"{k}="
                for k, v in [p.split("=", 1) for p in params.split("&") if p]
            )
            new_url = f"{base_url}{base_paths[base_org]}/mng.jsp?{encoded_params}"
            return new_url

        return urljoin(f"{base_url}{base_paths[base_org]}/", url)

    except Exception as e:
        logging.error(f"URL 수정 실패: {str(e)} - {url}")
        return url


def sanitize_filename(filename):
    """파일명에서 허용되지 않는 문자 제거"""
    import re

    # Windows에서 허용되지 않는 문자 제거
    s = re.sub(r'[<>:"/\\|?*]', "", filename)
    # 공백 문자를 언더스코어로 변경
    s = re.sub(r"\s+", "_", s)
    return s


def download_files(driver, df, base_download_path):
    """파일 다운로드"""
    # Chrome 다운로드 경로 설정을 위한 CDP 명령어 추가
    success_count = 0
    fail_count = 0
    progress_bar = st.progress(0)
    status_text = st.empty()
    time_info = st.empty()
    start_time = time.time()

    file_xpath = """//a[
        contains(@href, 'fileDownload') or 
        contains(@onclick, 'fileDownload') or 
        contains(@href, '.hwp') or 
        contains(@href, '.hwpx') or
        contains(@href, '.xls') or 
        contains(@href, '.xlsx') or
        contains(@href, '.doc') or 
        contains(@href, '.docx') or
        contains(@href, '.pdf') or
        contains(@href, '.ppt') or 
        contains(@href, '.pptx') or
        contains(@href, '.dwg') or 
        contains(@href, '.dxf') or
        contains(@href, '.zip')
    ]"""

    try:
        main_window = driver.current_window_handle

        for idx, row in df.iloc[:3].iterrows():
            if row["상세링크"]:
                # 넘버링이 포함된 폴더명 생성
                folder_name = sanitize_filename(f"{idx+1:02d}_{row['공사명']}")
                folder_path = os.path.join(base_download_path, folder_name)

                try:
                    os.makedirs(folder_path, exist_ok=True)
                    # st.info(f"생성된 폴더: {folder_path}")

                    # Chrome 다운로드 경로 설정
                    params = {"behavior": "allow", "downloadPath": folder_path}
                    driver.execute_cdp_cmd("Page.setDownloadBehavior", params)

                except Exception as e:
                    st.error(f"폴더 생성 실패: {str(e)}")
                    continue

                current_time = time.time()
                elapsed = current_time - start_time
                eta = (elapsed / (idx + 1)) * (3 - (idx + 1)) if idx < 2 else 0

                status_text.text(f"처리 중 ({idx+1}/3): {row['공사명']}")
                time_info.text(
                    f"경과 시간: {elapsed:.1f}초 | 예상 남은 시간: {eta:.1f}초"
                )

                try:
                    driver.execute_script(f"window.open('{row['상세링크']}');")
                    time.sleep(2)
                    driver.switch_to.window(driver.window_handles[-1])

                    elements = WebDriverWait(driver, 5).until(
                        EC.presence_of_all_elements_located((By.XPATH, file_xpath))
                    )

                    if elements:
                        # st.info(f"{len(elements)}개의 다운로드 링크 발견")

                        for elem in elements:
                            try:
                                driver.execute_script("arguments[0].click();", elem)
                                time.sleep(3)
                                success_count += 1
                                # st.success(f"파일 다운로드 성공")
                            except Exception as e:
                                st.warning(f"다운로드 실패: {str(e)}")
                                fail_count += 1
                    else:
                        st.warning("다운로드 링크를 찾을 수 없습니다.")
                        fail_count += 1

                finally:
                    driver.close()
                    driver.switch_to.window(main_window)
                    time.sleep(1)

            progress = (idx + 1) / min(3, len(df))
            progress_bar.progress(progress)

    finally:
        end_time = time.time()
        total_time = end_time - start_time
        time_info.text(f"총 소요 시간: {total_time:.1f}초")

        for handle in driver.window_handles:
            if handle != main_window:
                driver.switch_to.window(handle)
                driver.close()
        driver.switch_to.window(main_window)

    return success_count, fail_count


def get_bid_data(driver, selected_urls):
    """입찰 정보 수집"""
    all_data = []

    for org_name, url_path in selected_urls.items():
        try:
            url = f"https://www.molit.go.kr{url_path}"
            with st.spinner(f"{org_name} 데이터 수집 중..."):
                driver.get(url)
                time.sleep(2)

                soup = BeautifulSoup(driver.page_source, "html.parser")
                rows = soup.select("table tbody tr")

                for row in rows:
                    cols = row.find_all("td")
                    if len(cols) > 1:
                        try:
                            data = {
                                "기관명": org_name,
                                "번호": cols[0].get_text(strip=True),
                                "공사명": cols[1].get_text(strip=True),
                                "입찰공고번호": cols[2].get_text(strip=True),
                                "입찰일": cols[3].get_text(strip=True),
                                "등록일": cols[4].get_text(strip=True),
                            }

                            detail_link = cols[1].find("a")
                            if detail_link and "href" in detail_link.attrs:
                                data["상세링크"] = fix_detail_url(
                                    detail_link["href"], org_name
                                )
                            else:
                                data["상세링크"] = None

                            all_data.append(data)
                        except IndexError as e:
                            logging.error(f"행 데이터 처리 중 오류: {str(e)}")
                            continue

                logging.info(f"{org_name} 데이터 수집 완료")

        except Exception as e:
            logging.error(f"{org_name} 데이터 수집 실패: {str(e)}")
            st.error(f"데이터 수집 실패 ({org_name}): {str(e)}")

    df = pd.DataFrame(all_data)
    logging.info(f"생성된 데이터프레임 컬럼: {df.columns.tolist()}")
    # st.write("수집된 데이터 컬럼:", df.columns.tolist())
    return df


def setup_selenium():
    """Selenium WebDriver 설정"""
    from selenium.webdriver.chrome.service import Service
    from webdriver_manager.chrome import ChromeDriverManager
    from webdriver_manager.core.os_manager import ChromeType

    # Chrome 옵션 설정
    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")  # 새로운 headless 모드 사용
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")

    # 추가 안정성을 위한 옵션
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-software-rasterizer")
    options.add_argument("--remote-debugging-port=9222")

    # User-Agent 설정
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )

    try:
        # ChromeDriver 자동 설치 및 서비스 설정
        service = Service(
            ChromeDriverManager(chrome_type=ChromeType.CHROMIUM).install()
        )

        # WebDriver 초기화
        driver = webdriver.Chrome(service=service, options=options)

        # 암시적 대기 설정
        driver.implicitly_wait(10)

        return driver

    except Exception as e:
        st.error(f"ChromeDriver 초기화 실패: {str(e)}")
        logging.error(f"ChromeDriver 초기화 실패: {str(e)}")
        import traceback

        logging.error(traceback.format_exc())
        raise


def main():
    # 세션 상태 초기화
    if "bid_df" not in st.session_state:
        st.session_state["bid_df"] = None
    if "last_download_time" not in st.session_state:
        st.session_state["last_download_time"] = None

    # 사이드바 설정
    with st.sidebar:
        st.title("🔍 입찰정보 수집기")
        st.markdown("---")

        # 기관 선택
        st.subheader("📍 지방국토관리청")
        selected_regional = {
            k: st.checkbox(k, key=f"reg_{k}") for k in REGIONAL_OFFICES.keys()
        }

        st.markdown("---")
        st.subheader("💧 유역환경청")
        selected_river = {
            k: st.checkbox(k, key=f"river_{k}", disabled=True)
            for k in RIVER_OFFICES.keys()
        }

        # 다운로드 경로 설정
        st.markdown("---")
        default_download_path = os.path.join(os.path.expanduser("~"), "Downloads")
        download_path = st.text_input(
            "다운로드 경로",
            value=default_download_path,
            help="파일이 저장될 경로를 지정하세요.",
        )

        st.markdown("---")
        st.markdown("### 📊 실행 통계")
        stats_container = st.empty()

    # 메인 화면
    col1, col2 = st.columns([7, 3])

    with col1:
        if st.button("1. 입찰정보 수집", key="collect_data", use_container_width=True):
            # 선택된 기관 URL 필터링
            selected_urls = {
                **{k: REGIONAL_OFFICES[k] for k, v in selected_regional.items() if v},
                **{k: RIVER_OFFICES[k] for k, v in selected_river.items() if v},
            }

            if not selected_urls:
                st.warning("최소 하나 이상의 기관을 선택해주세요.")
                return

            start_time = time.time()
            driver = setup_selenium()

            try:
                df = get_bid_data(driver, selected_urls)
                st.session_state["bid_df"] = df

                end_time = time.time()
                collection_time = end_time - start_time

                with stats_container:
                    st.write(f"데이터 수집 시간: {collection_time:.1f}초")
                    st.write(f"수집된 데이터 수: {len(df)}건")

            except Exception as e:
                st.error(f"데이터 수집 중 오류 발생: {str(e)}")
            finally:
                driver.quit()

    with col2:
        if st.button(
            "2. 첨부파일 다운로드", key="download_files", use_container_width=True
        ):
            if st.session_state["bid_df"] is None:
                st.error("먼저 입찰정보를 수집해주세요.")
                return

            driver = setup_selenium()
            try:
                start_time = time.time()
                success, fail = download_files(
                    driver, st.session_state["bid_df"], download_path
                )
                end_time = time.time()
                download_time = end_time - start_time
                st.session_state["last_download_time"] = datetime.now()

                with stats_container:
                    st.write(f"파일 다운로드 시간: {download_time:.1f}초")
                    st.write(f"성공: {success}건, 실패: {fail}건")
                    if st.session_state["last_download_time"]:
                        st.write(
                            f"마지막 다운로드: {st.session_state['last_download_time'].strftime('%Y-%m-%d %H:%M:%S')}"
                        )

            except Exception as e:
                st.error(f"파일 다운로드 중 오류 발생: {str(e)}")
            finally:
                driver.quit()

    # 데이터 표시
    if st.session_state["bid_df"] is not None:
        st.markdown("### 📋 수집된 입찰정보")

        # 필터 옵션
        col1, col2 = st.columns(2)
        with col1:
            try:
                if "기관명" in st.session_state["bid_df"].columns:
                    unique_orgs = st.session_state["bid_df"]["기관명"].unique()
                    selected_orgs = st.multiselect(
                        "기관 필터링", options=unique_orgs, default=unique_orgs
                    )
                else:
                    st.error("데이터에 '기관명' 컬럼이 없습니다.")
                    selected_orgs = []
            except Exception as e:
                st.error(f"필터링 오류: {str(e)}")
                selected_orgs = []

        # 필터링된 데이터프레임
        try:
            if "기관명" in st.session_state["bid_df"].columns and selected_orgs:
                filtered_df = st.session_state["bid_df"][
                    st.session_state["bid_df"]["기관명"].isin(selected_orgs)
                ].copy()
            else:
                filtered_df = st.session_state["bid_df"].copy()
        except Exception as e:
            st.error(f"데이터 필터링 오류: {str(e)}")
            filtered_df = st.session_state["bid_df"].copy()

        # 상세링크 열 숨기기
        display_df = filtered_df.drop(columns=["상세링크"])

        # 데이터프레임 표시
        st.dataframe(display_df, use_container_width=True)

        # CSV 다운로드 버튼
        csv = filtered_df.to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            "CSV 다운로드",
            csv,
            f"입찰정보_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
            "text/csv",
            key="download-csv",
        )

    with st.expander("💡 사용 방법"):
        st.markdown(
            """
        1. 사이드바에서 원하는 기관들을 선택합니다.
        2. '입찰정보 수집' 버튼을 클릭하여 데이터를 수집합니다.
        3. 수집된 데이터를 확인하고 필요시 CSV로 다운로드합니다.
        4. '첨부파일 다운로드' 버튼을 클릭하여 선택된 공고의 첨부파일을 다운로드합니다.
        5. 다운로드된 파일은 지정된 다운로드 폴더에서 확인할 수 있습니다.
        """
        )


if __name__ == "__main__":
    main()
