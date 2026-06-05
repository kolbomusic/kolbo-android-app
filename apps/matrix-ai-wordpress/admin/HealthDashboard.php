<?php
if(!defined('ABSPATH')){exit;}

add_action('admin_menu', function() {
    add_submenu_page(
        'matrix-ai-settings',
        'Health & Monitoring',
        'Health Dashboard',
        'manage_options',
        'matrix-ai-health',
        'matrix_ai_health_dashboard'
    );
});

function matrix_ai_health_dashboard() {
    $health = MatrixAI_HealthCheck::getInstance();
    $status = $health->getStatus();
    $logger = MatrixAI_Logger::getInstance();
    $logs = $logger->getLogs(7);
    ?>
    <style>
        .health-wrap { direction: rtl; font-family: system-ui; padding: 20px; }
        .health-card { background: #fff; padding: 20px; border-radius: 8px; margin: 20px 0; border: 1px solid #e2e8f0; }
        .status-ok { color: #10b981; font-weight: bold; }
        .status-error { color: #ef4444; font-weight: bold; }
        .status-degraded { color: #f59e0b; font-weight: bold; }
        .health-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin: 20px 0; }
        .health-item { background: #f9fafb; padding: 15px; border-radius: 8px; border-left: 4px solid #e2e8f0; }
        .health-item.ok { border-left-color: #10b981; }
        .health-item.error { border-left-color: #ef4444; background: #fef2f2; }
        .log-box { background: #1f2937; color: #10b981; padding: 15px; border-radius: 8px; font-family: monospace; font-size: 12px; max-height: 400px; overflow-y: auto; margin: 10px 0; }
    </style>
    
    <div class="health-wrap">
        <h1>🏥 Matrix AI - Health Dashboard</h1>
        
        <div class="health-card">
            <h2>System Status</h2>
            <p>Overall Status: <span class="status-<?php echo $status['status']; ?>"><?php echo strtoupper($status['status']); ?></span></p>
            <div class="health-grid">
                <?php foreach($status['checks'] as $check => $result): ?>
                    <div class="health-item <?php echo $result; ?>">
                        <strong><?php echo ucfirst(str_replace('_', ' ', $check)); ?></strong><br>
                        <span class="status-<?php echo $result; ?>"><?php echo strtoupper($result); ?></span>
                    </div>
                <?php endforeach; ?>
            </div>
        </div>
        
        <div class="health-card">
            <h2>📋 Recent Logs</h2>
            <?php foreach(array_slice($logs, 0, 1) as $date => $log_content): ?>
                <p><strong>Date:</strong> <?php echo $date; ?></p>
                <div class="log-box"><?php echo esc_html($log_content); ?></div>
            <?php endforeach; ?>
        </div>
        
        <div class="health-card">
            <h2>🔧 Actions</h2>
            <form method="post" style="display: inline;">
                <?php wp_nonce_field('matrix_ai_maintenance', 'matrix_nonce'); ?>
                <input type="hidden" name="action" value="matrix_ai_optimize">
                <button type="submit" class="button button-primary">Optimize Database</button>
            </form>
            <form method="post" style="display: inline;">
                <?php wp_nonce_field('matrix_ai_maintenance', 'matrix_nonce'); ?>
                <input type="hidden" name="action" value="matrix_ai_cleanup">
                <button type="submit" class="button button-secondary">Cleanup Old Logs</button>
            </form>
        </div>
    </div>
    <?php
}

add_action('admin_init', function() {
    if(isset($_POST['action']) && isset($_POST['matrix_nonce'])) {
        if(!wp_verify_nonce($_POST['matrix_nonce'], 'matrix_ai_maintenance')) {
            wp_die('Security check failed');
        }
        
        $action = sanitize_text_field($_POST['action']);
        $db = MatrixAI_Database::getInstance();
        
        if($action === 'matrix_ai_optimize') {
            $db->optimize();
            wp_safe_remote_post(admin_url('admin-ajax.php'), [
                'blocking' => false,
                'sslverify' => apply_filters('https_local_ssl_verify', false)
            ]);
        } elseif($action === 'matrix_ai_cleanup') {
            $db->cleanup(90);
        }
    }
});
