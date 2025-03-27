import sys
import time
import random
import multiprocessing
import platform
from datetime import datetime
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QPushButton, QTableWidget, QVBoxLayout,
    QLabel, QWidget, QTableWidgetItem, QHBoxLayout, QSpinBox,
    QProgressBar, QMessageBox, QHeaderView, QComboBox, QGroupBox,
    QTabWidget, QTextEdit, QSystemTrayIcon, QMenu
)
from PyQt6.QtCore import QTimer, Qt, QThread, pyqtSignal
from PyQt6.QtGui import QColor, QBrush, QIcon, QAction
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import psutil


class SystemMonitorThread(QThread):
    """Thread to monitor system resources (CPU, memory, disk, network)."""
    update_signal = pyqtSignal(float, float, float, float)
    log_signal = pyqtSignal(str)  # New signal for logging

    def run(self):
        """Continuously fetch system stats and emit updates."""
        while True:
            try:
                cpu_usage = psutil.cpu_percent()
                memory_usage = psutil.virtual_memory().percent
                disk_usage = psutil.disk_usage('/').percent
                network_usage = psutil.net_io_counters().bytes_sent + psutil.net_io_counters().bytes_recv
                self.update_signal.emit(cpu_usage, memory_usage, disk_usage, network_usage)
                
                # Log system stats periodically
                if random.random() < 0.1:  # 10% chance to log system stats
                    self.log_signal.emit(
                        f"System Stats - CPU: {cpu_usage:.1f}%, "
                        f"Memory: {memory_usage:.1f}%, "
                        f"Disk: {disk_usage:.1f}%"
                    )
                    
            except Exception as e:
                self.log_signal.emit(f"System Monitor Error: {str(e)}")
                
            time.sleep(1)


class ProcessWorker(multiprocessing.Process):
    """Worker process that simulates work and communicates progress and status."""

    def __init__(self, process_id, status_queue, progress_queue, pause_event, stop_event, process_speed, priority, log_queue):
        super().__init__()
        self.process_id = process_id
        self.status_queue = status_queue
        self.progress_queue = progress_queue
        self.pause_event = pause_event
        self.stop_event = stop_event
        self.process_speed = process_speed
        self.priority = priority
        self.log_queue = log_queue  # Queue for log messages
        self.current_progress = 0
        self.start_time = None
        self.end_time = None

    def run(self):
        """Main execution loop for the worker process."""
        self.start_time = datetime.now()
        self.status_queue.put((self.process_id, "Running", self.priority))
        self.log_queue.put(f"Process {self.process_id} started (Priority: {self.priority}, Speed: {self.process_speed}x)")

        # Set process priority based on the operating system
        self.set_process_priority()

        while self.current_progress < 100 and not self.stop_event.is_set():
            if self.pause_event.is_set():
                self.status_queue.put((self.process_id, "Paused", self.priority))
                self.log_queue.put(f"Process {self.process_id} paused")
                while self.pause_event.is_set():
                    if self.stop_event.is_set():
                        self.status_queue.put((self.process_id, "Terminated", self.priority))
                        self.log_queue.put(f"Process {self.process_id} terminated while paused")
                        return
                    time.sleep(0.1)
                self.status_queue.put((self.process_id, "Resumed", self.priority))
                self.log_queue.put(f"Process {self.process_id} resumed")

            # Simulate work
            work_type = self.simulate_work()
            self.log_queue.put(f"Process {self.process_id} performing {work_type} work")

            # Update progress
            time.sleep(0.05 * (5 / self.process_speed))
            self.current_progress += 1
            self.progress_queue.put((self.process_id, self.current_progress))

        self.end_time = datetime.now()
        if not self.stop_event.is_set():
            duration = (self.end_time - self.start_time).total_seconds()
            self.status_queue.put((self.process_id, "Completed", self.priority, duration))
            self.log_queue.put(f"Process {self.process_id} completed in {duration:.2f} seconds")

    def set_process_priority(self):
        """Set the process priority based on the operating system."""
        try:
            if platform.system() == "Windows":
                import win32api
                import win32con
                priority_map = {
                    "Low": win32con.IDLE_PRIORITY_CLASS,
                    "Normal": win32con.NORMAL_PRIORITY_CLASS,
                    "High": win32con.HIGH_PRIORITY_CLASS
                }
                win32api.SetPriorityClass(win32api.GetCurrentProcess(), priority_map[self.priority])
            elif platform.system() == "Linux":
                import os
                niceness = {"Low": 19, "Normal": 10, "High": 0}[self.priority]
                os.nice(niceness)
        except Exception as e:
            self.status_queue.put((self.process_id, f"Priority Error: {str(e)}", self.priority))
            self.log_queue.put(f"Process {self.process_id} priority setting failed: {str(e)}")

    def simulate_work(self):
        """Simulate different types of work (CPU, memory, I/O)."""
        work_type = random.choice(['cpu', 'io', 'memory'])
        if work_type == 'cpu':
            [x * x for x in range(100000)]
        elif work_type == 'memory':
            _ = [0] * 100000
        else:
            time.sleep(0.01)
        return work_type


class ProcessSyncAnalyzer(QMainWindow):
    """Main GUI application for managing and monitoring worker processes."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Process Synchronization Analyzer")
        self.setGeometry(100, 100, 1200, 800)
        
        # Try to set window icon (optional)
        try:
            self.setWindowIcon(QIcon("icon.png"))
        except:
            pass

        # Initialize process management
        self.processes = []
        self.pause_event = multiprocessing.Event()
        self.stop_event = multiprocessing.Event()
        self.status_queue = multiprocessing.Queue()
        self.progress_queue = multiprocessing.Queue()
        self.log_queue = multiprocessing.Queue()  # Queue for log messages
        self.log_messages = []

        # System monitoring
        self.system_monitor = SystemMonitorThread()
        self.system_monitor.update_signal.connect(self.update_system_stats)
        self.system_monitor.log_signal.connect(self.log_message)  # Connect log signal

        # Set up UI
        self.init_ui()

        # Set up timers
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_ui)
        self.timer.start(200)  # Update UI every 200ms

        # Start system monitoring
        self.system_monitor.start()

    def init_ui(self):
        """Initialize the user interface."""
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QVBoxLayout(self.central_widget)

        # Create tabs
        self.tabs = QTabWidget()
        self.main_layout.addWidget(self.tabs)

        # Process Control Tab
        self.create_process_control_tab()

        # System Monitor Tab
        self.create_system_monitor_tab()

        # Log Tab
        self.create_log_tab()

        # Status bar
        self.status_bar = QLabel("Ready | System: ... | Processes: 0")
        self.main_layout.addWidget(self.status_bar)

    def create_process_control_tab(self):
        """Create the main process control tab."""
        control_tab = QWidget()
        layout = QVBoxLayout(control_tab)

        # Control panel
        control_group = QGroupBox("Process Controls")
        control_layout = QHBoxLayout()

        # Process configuration
        config_group = QGroupBox("Configuration")
        config_layout = QVBoxLayout()

        # Process count
        self.process_count = QSpinBox()
        self.process_count.setRange(1, 32)  # Limit to 32 processes max
        self.process_count.setValue(4)  # Default to 4 processes
        config_layout.addWidget(QLabel("Process Count:"))
        config_layout.addWidget(self.process_count)

        # Process speed
        self.process_speed = QComboBox()
        self.process_speed.addItems(["0.1x", "0.25x", "0.5x", "1x", "2x", "5x", "10x"])
        self.process_speed.setCurrentIndex(3)  # Default to 1x speed
        config_layout.addWidget(QLabel("Speed:"))
        config_layout.addWidget(self.process_speed)

        # Process priority
        self.process_priority = QComboBox()
        self.process_priority.addItems(["Low", "Normal", "High"])
        self.process_priority.setCurrentIndex(1)  # Default to Normal priority
        config_layout.addWidget(QLabel("Priority:"))
        config_layout.addWidget(self.process_priority)

        config_group.setLayout(config_layout)
        control_layout.addWidget(config_group)

        # Buttons
        button_layout = QVBoxLayout()

        self.start_btn = QPushButton("Start Processes")
        self.start_btn.clicked.connect(self.start_processes)
        button_layout.addWidget(self.start_btn)

        self.pause_btn = QPushButton("Pause All")
        self.pause_btn.clicked.connect(self.toggle_pause)
        self.pause_btn.setEnabled(False)  # Disabled until processes start
        button_layout.addWidget(self.pause_btn)

        self.stop_btn = QPushButton("Stop All")
        self.stop_btn.clicked.connect(self.stop_processes)
        self.stop_btn.setEnabled(False)  # Disabled until processes start
        button_layout.addWidget(self.stop_btn)

        control_layout.addLayout(button_layout)
        control_group.setLayout(control_layout)
        layout.addWidget(control_group)

        # Process table
        self.process_table = QTableWidget(0, 6, self)
        self.process_table.setHorizontalHeaderLabels([
            "Process ID", "Status", "Progress", "Speed", "Priority", "Duration"
        ])
        self.process_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.process_table.verticalHeader().setVisible(False)
        layout.addWidget(self.process_table)

        self.tabs.addTab(control_tab, "Process Control")

    def create_system_monitor_tab(self):
        """Create system monitoring tab with graphs."""
        monitor_tab = QWidget()
        layout = QVBoxLayout(monitor_tab)

        # CPU Usage
        self.cpu_figure = Figure()
        self.cpu_canvas = FigureCanvas(self.cpu_figure)
        self.cpu_ax = self.cpu_figure.add_subplot(111)
        self.cpu_data = [0] * 60  # Store last 60 data points (1 minute at 1s intervals)
        layout.addWidget(QLabel("CPU Usage (%)"))
        layout.addWidget(self.cpu_canvas)

        # Memory Usage
        self.mem_figure = Figure()
        self.mem_canvas = FigureCanvas(self.mem_figure)
        self.mem_ax = self.mem_figure.add_subplot(111)
        self.mem_data = [0] * 60  # Store last 60 data points
        layout.addWidget(QLabel("Memory Usage (%)"))
        layout.addWidget(self.mem_canvas)

        self.tabs.addTab(monitor_tab, "System Monitor")

    def create_log_tab(self):
        """Create logging tab with timestamped messages."""
        log_tab = QWidget()
        layout = QVBoxLayout(log_tab)

        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        layout.addWidget(self.log_view)

        # Clear log button
        clear_btn = QPushButton("Clear Log")
        clear_btn.clicked.connect(self.clear_log)
        layout.addWidget(clear_btn)

        self.tabs.addTab(log_tab, "Event Log")

    def start_processes(self):
        """Start processes with advanced configuration."""
        self.stop_processes()  # Clean up any existing processes

        # Reset events and counters
        self.pause_event.clear()
        self.stop_event.clear()
        self.completed_processes = 0

        # Get configuration
        num_processes = self.process_count.value()
        speed_map = {
            "0.1x": 0.1, "0.25x": 0.25, "0.5x": 0.5,
            "1x": 1.0, "2x": 2.0, "5x": 5.0, "10x": 10.0
        }
        speed = speed_map[self.process_speed.currentText()]
        priority = self.process_priority.currentText()

        # Initialize table
        self.process_table.setRowCount(num_processes)

        # Create processes
        for i in range(num_processes):
            process = ProcessWorker(
                i, self.status_queue, self.progress_queue,
                self.pause_event, self.stop_event, speed, priority,
                self.log_queue  # Pass the log queue to each process
            )
            self.processes.append(process)

            # Initialize table row
            self.process_table.setItem(i, 0, QTableWidgetItem(str(i)))
            self.process_table.setItem(i, 1, QTableWidgetItem("Starting"))
            self.process_table.item(i, 1).setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            # Progress bar
            progress_bar = QProgressBar()
            progress_bar.setRange(0, 100)
            progress_bar.setValue(0)
            self.process_table.setCellWidget(i, 2, progress_bar)

            # Speed and priority
            self.process_table.setItem(i, 3, QTableWidgetItem(self.process_speed.currentText()))
            self.process_table.setItem(i, 4, QTableWidgetItem(priority))
            self.process_table.setItem(i, 5, QTableWidgetItem(""))

            process.start()

        # Update UI
        self.start_btn.setEnabled(False)
        self.pause_btn.setEnabled(True)
        self.stop_btn.setEnabled(True)
        self.status_bar.setText(f"Running {num_processes} processes | Priority: {priority}")
        
        # Log process start
        self.log_message(f"Started {num_processes} processes (Speed: {self.process_speed.currentText()}, Priority: {priority})")

    def toggle_pause(self):
        """Toggle pause state with immediate effect."""
        if self.pause_event.is_set():
            self.pause_event.clear()
            self.pause_btn.setText("Pause All")
            self.status_bar.setText(self.status_bar.text().replace("Paused", "Running"))
            self.log_message("All processes resumed")
        else:
            self.pause_event.set()
            self.pause_btn.setText("Resume All")
            self.status_bar.setText(self.status_bar.text().replace("Running", "Paused"))
            self.log_message("All processes paused")

    def stop_processes(self):
        """Stop all processes with cleanup."""
        if not self.processes:
            return

        self.stop_event.set()
        self.log_message("Stopping all processes...")

        for i, process in enumerate(self.processes):
            # Update status to "Terminating" immediately
            self.update_process_status(i, "Terminating")
            self.process_table.item(i, 1).setText("Terminating")
            
            process.join(timeout=1)
            if process.is_alive():
                process.terminate()
                self.update_process_status(i, "Terminated")
                self.process_table.item(i, 1).setText("Terminated")
            else:
                self.update_process_status(i, "Terminated")
                self.process_table.item(i, 1).setText("Terminated")

        # Clean up
        self.processes = []
        self.pause_event.clear()
        self.stop_event.clear()

        # Clear queues to prevent stale messages
        while not self.status_queue.empty():
            self.status_queue.get()
        while not self.progress_queue.empty():
            self.progress_queue.get()
        while not self.log_queue.empty():
            self.log_queue.get()

        # Reset UI
        self.start_btn.setEnabled(True)
        self.pause_btn.setEnabled(False)
        self.stop_btn.setEnabled(False)
        self.pause_btn.setText("Pause All")
        self.status_bar.setText("Ready")
        self.log_message("All processes stopped")

    def update_ui(self):
        """Update UI from queue data."""
        # Process status updates
        while not self.status_queue.empty():
            data = self.status_queue.get()
            pid = data[0]
            status = data[1]

            if status == "Completed":
                priority = data[2]
                duration = data[3]
                self.update_process_status(pid, status, priority)
                self.process_table.setItem(pid, 5, QTableWidgetItem(f"{duration:.2f}s"))
            else:
                priority = data[2] if len(data) > 2 else "Normal"
                self.update_process_status(pid, status, priority)

        # Process progress updates
        while not self.progress_queue.empty():
            pid, progress = self.progress_queue.get()
            progress_bar = self.process_table.cellWidget(pid, 2)
            if progress_bar:
                progress_bar.setValue(progress)

        # Process log messages
        while not self.log_queue.empty():
            message = self.log_queue.get()
            self.log_message(message)

    def update_process_status(self, pid, status, priority="Normal"):
        """Update status with color coding."""
        item = self.process_table.item(pid, 1)
        if item:
            item.setText(status)

            # Color coding for different statuses
            color_map = {
                "Running": QColor(50, 150, 50),  # Green
                "Paused": QColor(200, 200, 0),  # Yellow
                "Completed": QColor(70, 130, 180),  # Steel blue
                "Terminated": QColor(200, 50, 50),  # Red
                "Terminating": QColor(200, 100, 50),  # Orange
                "Error": QColor(200, 100, 0)  # Orange
            }
            item.setBackground(QBrush(color_map.get(status, QColor(0, 100, 0))))

    def update_system_stats(self, cpu, mem, disk, net):
        """Update system monitoring graphs."""
        # Update CPU graph
        self.cpu_data = self.cpu_data[1:] + [cpu]
        self.cpu_ax.clear()
        self.cpu_ax.plot(self.cpu_data, 'r-')
        self.cpu_ax.set_ylim(0, 100)
        self.cpu_ax.set_title("CPU Usage (%)")
        self.cpu_canvas.draw()

        # Update Memory graph
        self.mem_data = self.mem_data[1:] + [mem]
        self.mem_ax.clear()
        self.mem_ax.plot(self.mem_data, 'b-')
        self.mem_ax.set_ylim(0, 100)
        self.mem_ax.set_title("Memory Usage (%)")
        self.mem_canvas.draw()

    def log_message(self, message):
        """Add a timestamped message to the log."""
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        log_entry = f"[{timestamp}] {message}"
        self.log_messages.append(log_entry)
        self.log_view.append(log_entry)
        
        # Auto-scroll to bottom
        scrollbar = self.log_view.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def clear_log(self):
        """Clear the event log."""
        self.log_messages = []
        self.log_view.clear()
        self.log_message("Log cleared")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle('Fusion')  # Use Fusion style for modern look
    window = ProcessSyncAnalyzer()
    window.show()
    sys.exit(app.exec())