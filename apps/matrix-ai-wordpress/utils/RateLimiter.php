<?php
if(!defined('ABSPATH')){exit;}

class MatrixAI_RateLimiter {
    private static $instance = null;
    private $limit = MATRIX_AI_RATE_LIMIT;
    private $window = 3600; // 1 hour
    
    private function __construct() {}
    
    public static function getInstance() {
        if(self::$instance === null) {
            self::$instance = new self();
        }
        return self::$instance;
    }
    
    public function isAllowed($identifier) {
        $cache = MatrixAI_Cache::getInstance();
        $key = 'rate_limit_'.$identifier;
        
        $count = $cache->get($key, 0);
        
        if($count >= $this->limit) {
            return false;
        }
        
        $cache->set($key, $count + 1, $this->window);
        return true;
    }
    
    public function getRemainingRequests($identifier) {
        $cache = MatrixAI_Cache::getInstance();
        $key = 'rate_limit_'.$identifier;
        $count = $cache->get($key, 0);
        return max(0, $this->limit - $count);
    }
    
    public function reset($identifier) {
        $cache = MatrixAI_Cache::getInstance();
        $cache->delete('rate_limit_'.$identifier);
        return true;
    }
}
