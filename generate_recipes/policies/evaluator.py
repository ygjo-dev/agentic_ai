from abc import ABC, abstractmethod

class BaseEvaluator(ABC):
    @abstractmethod
    def evaluate(self, condition, state):
        pass


# 숫자 비교 Evaluator
class CompareEvaluator(BaseEvaluator):
  OPERATORS = {
      ">=": lambda a, b: a >= b,
      ">":  lambda a, b: a > b,
      "<=": lambda a, b: a <= b,
      "<":  lambda a, b: a < b,
      "==": lambda a, b: a == b,
      "!=": lambda a, b: a != b,
      "in": lambda a, b: a in b,
  }

  def evaluate(self, condition, state):
      field = condition["field"]
      current = state.get(field)
      operator = condition["operator"]
      target = condition["value"]
      compare_func = self.OPERATORS.get(operator)

      if compare_func is None:
          raise ValueError(
              f"Unsupported operator: {operator}"
          )
      
      return compare_func(
          current,
          target
      )

# Event Evaluator
class EventEvaluator(BaseEvaluator):
    def evaluate(self, condition, state):
        target_event = condition["event"]
        events = state.get(
            "events",
            []
        )
        return target_event in events

class Evaluator:
    def __init__(self):
        self.handlers = {
            "compare":
                CompareEvaluator(),
            "event":
                EventEvaluator()
        }

    def evaluate(
        self,
        condition,
        state
    ):
        condition_type = condition["type"]
        evaluator = self.handlers.get(
            condition_type
        )

        if evaluator is None:
            raise Exception(
                f"Unsupported condition type: {condition_type}"
            )

        return evaluator.evaluate(
            condition,
            state
        )