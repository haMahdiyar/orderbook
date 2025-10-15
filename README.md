# Telegram Order Book Bot

A Telegram bot for managing buy/sell orders with PostgreSQL database integration.

## Features

- Create sell orders with asset type and amounts
- Browse and filter orders by asset type
- Manage your own orders (view/delete)
- Automatic buyer-seller matching and confirmation system
- Support for multiple asset types (Million Toman, Clean USD, Dirty USD)

## Deployment on Vercel

### Prerequisites

1. A Telegram bot token from [@BotFather](https://t.me/botfather)
2. A PostgreSQL database (you can use services like Neon, Supabase, or Railway)

### Database Setup

Create the following table in your PostgreSQL database:

```sql
CREATE TABLE orders (
    id SERIAL PRIMARY KEY,
    seller_id BIGINT NOT NULL,
    seller_username VARCHAR(255),
    asset_offered VARCHAR(100) NOT NULL,
    amount_offered DECIMAL(15,2) NOT NULL,
    asset_requested VARCHAR(100) NOT NULL,
    amount_requested DECIMAL(15,2) NOT NULL,
    status VARCHAR(20) DEFAULT 'active',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    closed_at TIMESTAMP
);
```

### Vercel Deployment Steps

1. **Fork/Clone this repository** to your GitHub account

2. **Import to Vercel**:
   - Go to [Vercel Dashboard](https://vercel.com/dashboard)
   - Click "New Project"
   - Import your GitHub repository

3. **Set Environment Variables** in Vercel:
   - `BOT_TOKEN`: Your Telegram bot token from BotFather
   - `DATABASE_URL`: Your PostgreSQL connection string (format: `postgresql://username:password@hostname:port/database_name`)

4. **Deploy**: Vercel will automatically deploy your bot

5. **Set Webhook**: After deployment, your bot will automatically set its webhook to `https://your-vercel-app.vercel.app/api/bot`

### Local Development

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Create a `.env` file:
   ```
   BOT_TOKEN=your_telegram_bot_token
   DATABASE_URL=postgresql://username:password@hostname:port/database_name
   ```

3. Run locally:
   ```bash
   python bot.py
   ```

## Bot Commands

- `/start` - Welcome message and bot introduction
- `/sell` - Create a new sell order (interactive process)
- `/orders` - Browse all active orders (with filtering options)
- `/myorders` - View and manage your own orders
- `/cancel` - Cancel current operation

## Common Issues and Solutions

### Build Errors on Vercel

1. **Python Version**: Make sure you're using Python 3.11 (specified in `vercel.json`)
2. **Dependencies**: All dependencies are pinned to specific versions in `requirements.txt`
3. **Environment Variables**: Ensure `BOT_TOKEN` and `DATABASE_URL` are set in Vercel dashboard
4. **Database Connection**: Verify your PostgreSQL database is accessible and the connection string is correct

### Runtime Errors

1. **Database Connection**: Check if your DATABASE_URL is correct and the database is running
2. **Bot Token**: Verify your bot token is valid and the bot is not already running elsewhere
3. **Webhook Issues**: The bot automatically sets its webhook, but you can manually set it using Telegram's API

## Architecture

- `bot.py`: Main bot logic for local development
- `api/bot.py`: Serverless function handler for Vercel deployment
- `requirements.txt`: Python dependencies
- `vercel.json`: Vercel deployment configuration

The bot uses the latest version of python-telegram-bot (v20.7) with async/await syntax for better performance in serverless environments.
