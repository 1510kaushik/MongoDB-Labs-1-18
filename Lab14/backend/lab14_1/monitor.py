from .service import write_metrics_log

if __name__ == "__main__":
    print("Lab 14.1 monitoring started. Logging every 30 seconds.")
    write_metrics_log()
