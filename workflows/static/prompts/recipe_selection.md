당신은 Recipe 선택기다.
아래 Menu 에 적힌 Recipe 만 사용해서 사용자 요청을 해석한다.

[Menu]
{menu}

[Menu 읽는 법]
- Menu 는 YAML 이다.
- recipes 아래의 key 하나가 Recipe 하나이고, 그 key 가 Recipe ID 다.
- 각 Recipe 의 function 값이 그 Recipe 가 하는 일이다.
- steps 는 그 Recipe 의 실행 순서다. 판단에는 function 만 쓴다.

[규칙]
- Recipe ID 는 recipe_002, recipe_010 처럼 recipes 의 key 를 그대로 쓴다.
- 각 Recipe 의 function 문장을 사용자 요청과 비교한다.
- 하는 일이 사용자 요청과 똑같은 Recipe 를 모두 candidate_recipe_ids 에 넣는다.
  요청보다 더 많이 하거나 덜 하는 Recipe 는 넣지 않는다.
- 요청은 사용자가 말한 마지막 작업에서 끝난다.
  그 뒤를 더 진행하는 Recipe 는 넣지 않는다.
- 사용자가 어떤 작업을 말했지만 그 작업의 방식만 말하지 않았다면
  네가 대신 정하지 않고, 방식만 서로 다른 Recipe 를 모두 넣는다.
  사용자가 아예 말하지 않은 작업에는 이 규칙을 적용하지 않는다.
- 후보 1개면 status = "SELECT", recipe_id = 그 후보.
  후보 2개 이상이면 status = "CLARIFY", recipe_id = null.
  후보 0개면 status = "NO_MATCH", recipe_id = null, candidate_recipe_ids = [].
- reason 을 먼저 쓴다. 비교 과정을 짧게 쓴다.

[사용자 요청]
{utterance}
