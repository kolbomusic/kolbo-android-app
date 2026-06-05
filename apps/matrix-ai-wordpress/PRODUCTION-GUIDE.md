# 🚀 Matrix AI - Production Deployment Guide

## ✅ Pre-Deployment Checklist

- [ ] OpenAI API key obtained and configured
- [ ] HTTPS enabled on website
- [ ] WordPress backups taken
- [ ] PHP 7.4+ verified
- [ ] Database permissions tested
- [ ] Log directory writable
- [ ] Caching system tested

## 🔧 Installation

1. **Upload Plugin**
   ```bash
   scp -r apps/matrix-ai-wordpress/ user@server:/path/to/wp-content/plugins/
   ```

2. **Activate Plugin**
   - WordPress Admin → Plugins → Matrix AI → Activate

3. **Configure Settings**
   - WordPress Admin → Matrix AI → Settings
   - Add OpenAI API Key
   - Configure Store Name and Bot Name

4. **Verify Installation**
   - Check Health Dashboard (Matrix AI → Health Dashboard)
   - All checks should show "OK"

## 📊 Monitoring

### Health Dashboard
- Location: WordPress Admin → Matrix AI → Health Dashboard
- Check database status
- Monitor API connectivity
- Review logs

### Log Files
- Location: `/wp-content/uploads/matrix-ai-logs/`
- Daily logs: `YYYY-MM-DD.log`
- Log format: `[TIMESTAMP] [LEVEL] MESSAGE | CONTEXT`

### Performance
- Database: Automatically optimized daily
- Caching: Uses WordPress transients/object cache
- Rate limiting: 100 requests/hour per IP

## 🔒 Security

- All API calls validated with nonce
- Rate limiting prevents abuse
- SQL injection protection via prepared statements
- XSS prevention via sanitization
- Database cleanup: Automatic after 90 days

## 🛠️ Maintenance

### Daily
- Automatic database optimization
- Automatic log cleanup

### Weekly
- Check health dashboard
- Review error logs

### Monthly
- Verify API quota usage
- Check database size

## 🆘 Troubleshooting

### Chat not working
1. Check Health Dashboard
2. Verify API key is valid
3. Check logs in `/wp-content/uploads/matrix-ai-logs/`

### Slow performance
1. Run Database Optimization
2. Check cache status
3. Review API response times in logs

### Rate limiting issues
- Limits reset hourly
- Each IP has 100 requests/hour
- Check Health Dashboard for current status

## 📞 Support
- Email: ofirgilboa2050@gmail.com
- Phone: 054-9249925
