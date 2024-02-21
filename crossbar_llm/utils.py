from timeit import default_timer as timer

def timer_func(func):
    def wrapper(*args, **kwargs):
        t1 = timer()
        result = func(*args, **kwargs)
        t2 = timer()
        print(f'{func.__name__}() executed in {(t2-t1):.6f}s')
        return result
    return wrapper
