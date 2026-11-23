# 무료 공개 원문으로 검토한 문헌

2026-11-23 기준으로 비용·기관 구독 없이 본문을 읽을 수 있는 출판사 공개 논문 또는 공공기관의 저자 원고만 선정했다. `2026. 과학 과제 연구 보고서_최종-1.pdf` 11–12쪽의 참고 문헌 7편과 앞서 프로그램에 적은 논문은 제외했다. 아래 링크는 무료 본문으로 연결된다.

## 1. 담수에서의 흡광도비 관계식

**Lai, C.-Z., DeGrandpre, M. D., Wasser, B. D., Brandon, T. A., Clucas, D. S., Jaqueth, E. J., Benson, Z. D., Beatty, C. M., & Spaulding, R. S. (2016).**

**Spectrophotometric measurement of freshwater pH with purified meta-cresol purple and phenol red.**

**Limnology and Oceanography: Methods, 14(12), 864–873.**

**DOI: [10.1002/lom3.10137](https://aslopubs.onlinelibrary.wiley.com/doi/10.1002/lom3.10137)**

공개 형태: 출판사 Open Access 본문.

검토 부분: Theory의 식 (3)–(6), Spectrophotometric measurements, Discussions, implications, and recommendations. 정제 mCP의 관계식은 온도와 이온 세기를 고려하며, 식 (5)의 적용 범위는 이온 세기 0.05 M 이하이다. 현재 0.40–1.60 M NaCl 조건에 이 식을 그대로 적용하지 않는다. 0 M 시료도 첨가한 다른 물질 때문에 이온 세기 0이라고 가정할 수 없다.

계수의 유효숫자와 지수를 바로잡은 [2017년 정정문](https://aslopubs.onlinelibrary.wiley.com/doi/10.1002/lom3.10210)도 함께 확인했다. 정정문은 *Limnology and Oceanography: Methods, 15(10), 903*, DOI **10.1002/lom3.10210**이며 무료 공개되어 있다. 이 프로그램에는 해당 계수를 입력하지 않았다.

## 2. 지시약 첨가에 따른 pH 변화

**Li, X., García-Ibáñez, M. I., Carter, B. R., Chen, B., Li, Q., Easley, R. A., & Cai, W.-J. (2020).**

**Purified meta-Cresol Purple dye perturbation: How it influences spectrophotometric pH measurements.**

**Marine Chemistry, 225, 103849.**

**DOI: [10.1016/j.marchem.2020.103849](https://repository.library.noaa.gov/view/noaa/57976)**

공개 형태: NOAA 저장소의 [무료 저자 원고 PDF](https://repository.library.noaa.gov/view/noaa/57976/noaa_57976_DS1.pdf).

검토 부분: Theory and Method, Discussion 4.1 및 4.3, Conclusions. 지시약 첨가에 따른 pH 변화는 시료와 지시약의 조성에 따라 달라졌다. 제공된 이론 보정 프로그램은 시료의 총알칼리도·용존무기탄소·염분·온도, 지시약의 성질, 혼합 부피 등의 입력을 요구한다. 이 정보가 없는 현재 실험에 보정값을 임의로 부여하지 않는다. 또한 논문의 pH 오차를 NaCl 몰농도 오차로 해석하지 않는다.

## 3. 배경 흡광도와 지시약 불순물

**Rivaro, P., Vivado, D., Falco, P., & Ianni, C. (2021).**

**HPLC-DAD Purification and Characterization of Meta-Cresol-Purple for Spectrophotometric Seawater pH Measurements.**

**Water, 13(21), 3030.**

**DOI: [10.3390/w13213030](https://www.mdpi.com/2073-4441/13/21/3030)**

공개 형태: 출판사 Open Access 본문, CC BY.

검토 부분: 2.5 및 3.1. 지시약을 넣기 전 배경 흡광도와 730 nm 측정값으로 바탕선 변화를 보정했다. HPLC로 분리한 불순물의 파장별 흡수도 확인했다. 프로그램에는 이 중 일정한 바탕선 오프셋을 빼는 처리만 참고하여 구현했다. 실제 측정점 730.1 nm 값을 두 파장의 흡광도에서 각각 빼고 비율을 구하며, 검량자료와 입력 시료에 동일하게 적용한다. 지시약 없는 블랭크를 측정하지 않았으므로 논문의 전체 배경 보정을 재현한 것은 아니다. 파장에 따른 배경 변화나 불순물, pH·온도의 영향은 이 처리로 제거되었다고 볼 수 없다.

## 현재 계산에 사용되는 자료

기본 검량선은 2026-11-05에 측정한 3차 실험의 8개 표준시료에서 얻었다. 원본 CSV에서 확인한 730.1 nm 흡광도를 보정에 사용하며, 외부 논문의 원시 측정값을 현재 실험의 기준점에 합산하지 않았다. 사용자가 새 검량자료를 불러오면 각 측정값에 같은 보정을 적용한 뒤 농도별 평균 흡광도비로 기준 곡선을 갱신한다. 보정을 해제하면 원래 흡광도비를 사용한다.

목표 오차 ±0.30 M의 충족 여부는 제공된 검증 시료의 결과로 확인한다. pH·온도가 미측정인 임의의 시료에 대해 이 목표를 보장할 근거는 현재 없다.

## 소프트웨어 구현 문서

PCHIP 구현은 무료로 공개된 [SciPy PchipInterpolator 공식 문서](https://docs.scipy.org/doc/scipy/reference/generated/scipy.interpolate.PchipInterpolator.html)를 확인했다. 이는 학술 논문 목록과 별개인 사용 라이브러리의 설명서이다. 바탕선 보정 모드에서도 PCHIP 역산 방법을 사용하며, 보정된 비율로 검량선을 다시 구성한다.
