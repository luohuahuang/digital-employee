try:
    from .evaluator import run_exam, run_all_exams
    __all__ = ["run_exam", "run_all_exams"]
except ImportError:
    pass
