<?php
if(!defined('ABSPATH')){exit;}

class MatrixAI_HealthCheck {
    private static $instance = null;
    private $logger;
    private $cache;
    
    private function __construct() {
        $this->logger = MatrixAI_Logger::getInstance();
        $this->cache = MatrixAI_Cache::getInstance();
    }
    
    public static function getInstance() {
        if(self::$instance === null) {
            self::$instance = new self();
        }
        return self::$instance;
    }
    
    public function check() {
        $status = [
            'status' => 'healthy',
            'checks' => [],
            'timestamp' => current_time('mysql')
        ];
        
        // API Key Check
        $api_key = get_option('matrix_ai_key');
        $status['checks']['api_key'] = !empty($api_key) ? 'ok' : 'missing';
        if($status['checks']['api_key'] === 'missing') {
            $status['status'] = 'degraded';
        }
        
        // Database Check
        global $wpdb;
        try {
            $wpdb->get_var("SELECT 1");
            $status['checks']['database'] = 'ok';
        } catch(Exception $e) {
            $status['checks']['database'] = 'error';
            $status['status'] = 'critical';
        }
        
        // Cache Check
        $cache_test = $this->cache->set('health_check_test', 'ok', 10);
        $cache_get = $this->cache->get('health_check_test');
        $status['checks']['cache'] = ($cache_get === 'ok') ? 'ok' : 'error';
        
        // Tables Check
        $tables_ok = true;
        foreach(['matrix_leads', 'matrix_chat_logs'] as $table) {
            $table_name = $wpdb->prefix.$table;
            if(!$wpdb->get_var("SHOW TABLES LIKE '$table_name'")) {
                $tables_ok = false;
            }
        }
        $status['checks']['tables'] = $tables_ok ? 'ok' : 'error';
        if(!$tables_ok) {
            $status['status'] = 'critical';
        }
        
        // Permissions Check
        $upload_dir = wp_upload_dir();
        $log_dir = MATRIX_AI_LOG_DIR;
        $status['checks']['log_dir'] = is_writable($log_dir) ? 'ok' : 'error';
        if($status['checks']['log_dir'] === 'error') {
            $status['status'] = 'degraded';
        }
        
        // Cache the status
        $this->cache->set('health_status', $status, 300);
        
        return $status;
    }
    
    public function getStatus() {
        $cached = $this->cache->get('health_status');
        if($cached !== null) {
            return $cached;
        }
        return $this->check();
    }
}
