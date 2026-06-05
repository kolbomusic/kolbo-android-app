<?php
if(!defined('ABSPATH')){exit;}

class MatrixAI_Logger {
    private static $instance = null;
    private $log_file;
    
    private function __construct() {
        $this->log_file = MATRIX_AI_LOG_DIR.'/'.date('Y-m-d').'.log';
    }
    
    public static function getInstance() {
        if(self::$instance === null) {
            self::$instance = new self();
        }
        return self::$instance;
    }
    
    public function info($message, $context = []) {
        $this->write('INFO', $message, $context);
    }
    
    public function error($message, $context = []) {
        $this->write('ERROR', $message, $context);
        error_log('[Matrix AI] '.$message);
    }
    
    public function warning($message, $context = []) {
        $this->write('WARNING', $message, $context);
    }
    
    public function debug($message, $context = []) {
        if(MATRIX_AI_DEBUG) {
            $this->write('DEBUG', $message, $context);
        }
    }
    
    private function write($level, $message, $context) {
        $timestamp = current_time('Y-m-d H:i:s');
        $context_str = !empty($context) ? ' | '.json_encode($context) : '';
        $log_line = "[$timestamp] [$level] $message$context_str\n";
        
        if(file_exists(dirname($this->log_file))) {
            @file_put_contents($this->log_file, $log_line, FILE_APPEND);
        }
    }
    
    public function getLogs($days = 7) {
        $logs = [];
        for($i = 0; $i < $days; $i++) {
            $date = date('Y-m-d', strtotime("-$i days"));
            $file = MATRIX_AI_LOG_DIR.'/'.$date.'.log';
            if(file_exists($file)) {
                $logs[$date] = file_get_contents($file);
            }
        }
        return $logs;
    }
}
