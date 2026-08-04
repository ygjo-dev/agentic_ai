import yaml
from engine.evaluator import Evaluator

class DecisionNode:
    def __init__(self, policy_path):
        self.policy_path = policy_path
        self.evaluator = Evaluator()

    def execute(self, state):
        policy = self.load_policy()
        for rule in policy["rules"]:
            matched = self.evaluator.evaluate(
                rule["condition"],
                state
            )
            if matched:
                return rule["action"]["node"]
            
        return None

    def load_policy(self):
        with open(
            self.policy_path,
            encoding="utf-8"
        ) as f:
            return yaml.safe_load(f)