<?php
if(!defined('ABSPATH')){exit;}

add_action('admin_menu', function() {
    add_menu_page(
        'Matrix AI',
        'Matrix AI',
        'manage_options',
        'matrix-ai-settings',
        'matrix_ai_render_settings',
        'dashicons-format-chat',
        58
    );
});

function matrix_ai_render_settings() {
    if(!current_user_can('manage_options')) {
        wp_die('Unauthorized');
    }
    
    if(isset($_POST['submit'])) {
        check_admin_referer('matrix_ai_settings_nonce', 'matrix_nonce');
        
        update_option('matrix_ai_key', sanitize_text_field($_POST['matrix_ai_key'] ?? ''));
        update_option('matrix_ai_store_name', sanitize_text_field($_POST['matrix_ai_store_name'] ?? ''));
        update_option('matrix_ai_bot_name', sanitize_text_field($_POST['matrix_ai_bot_name'] ?? ''));
        
        MatrixAI_Logger::getInstance()->info('Settings updated by admin');
    }
    ?>
    <style>
        .matrix-wrap { direction: rtl; font-family: system-ui; padding: 20px; max-width: 1200px; }
        .matrix-card { background: #fff; padding: 20px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); margin: 20px 0; }
        .form-group { margin: 15px 0; }
        .form-group label { display: block; font-weight: bold; margin-bottom: 5px; }
        .form-group input { width: 100%; max-width: 500px; padding: 10px; border: 1px solid #ddd; border-radius: 4px; }
        .submit-btn { background: #0073aa; color: #fff; padding: 10px 20px; border: none; border-radius: 4px; cursor: pointer; font-weight: bold; }
        .submit-btn:hover { background: #005a87; }
        .alert { padding: 12px; border-radius: 4px; margin: 10px 0; }
        .alert-info { background: #e7f3ff; border-left: 4px solid #0073aa; color: #0073aa; }
    </style>
    
    <div class="matrix-wrap">
        <h1>🤖 Matrix AI Configuration</h1>
        
        <div class="alert alert-info">
            <strong>ℹ️ Info:</strong> Configure your settings below. Make sure to get your OpenAI API key from <a href="https://platform.openai.com/api-keys" target="_blank">platform.openai.com</a>
        </div>
        
        <form method="post" class="matrix-card">
            <?php wp_nonce_field('matrix_ai_settings_nonce', 'matrix_nonce'); ?>
            
            <div class="form-group">
                <label for="matrix_ai_key">OpenAI API Key:</label>
                <input type="password" id="matrix_ai_key" name="matrix_ai_key" value="<?php echo esc_attr(get_option('matrix_ai_key', '')); ?>" placeholder="sk-...">
            </div>
            
            <div class="form-group">
                <label for="matrix_ai_store_name">Store Name:</label>
                <input type="text" id="matrix_ai_store_name" name="matrix_ai_store_name" value="<?php echo esc_attr(get_option('matrix_ai_store_name', '')); ?>" placeholder="Your Store Name">
            </div>
            
            <div class="form-group">
                <label for="matrix_ai_bot_name">Bot Name:</label>
                <input type="text" id="matrix_ai_bot_name" name="matrix_ai_bot_name" value="<?php echo esc_attr(get_option('matrix_ai_bot_name', '')); ?>" placeholder="Bot Name">
            </div>
            
            <button type="submit" name="submit" class="submit-btn">Save Settings</button>
        </form>
    </div>
    <?php
}
