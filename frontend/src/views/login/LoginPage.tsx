import { useState } from 'react'
import { Form, Input, Button, Checkbox, Card, Typography, message, Steps } from 'antd'
import { UserOutlined, LockOutlined, SafetyOutlined, MobileOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import './LoginPage.css'

const { Title, Text, Link } = Typography

// 登录表单
interface LoginFormData {
  username: string
  password: string
  remember: boolean
}

// 找回密码步骤
enum ForgotStep {
  INPUT_PHONE = 0,
  VERIFY_CODE = 1,
  SET_PASSWORD = 2,
  SUCCESS = 3
}

export default function LoginPage() {
  const navigate = useNavigate()
  const [loading, setLoading] = useState(false)
  const [showForgot, setShowForgot] = useState(false)
  const [forgotStep, setForgotStep] = useState<ForgotStep>(ForgotStep.INPUT_PHONE)
  const [phone, setPhone] = useState('')
  const [countdown, setCountdown] = useState(0)

  // 登录提交
  const handleLogin = async (values: LoginFormData) => {
    setLoading(true)
    try {
      // TODO: 调用登录API
      const response = await fetch('/api/v1/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          username: values.username,
          password: values.password
        })
      })
      
      const data = await response.json()
      
      if (!response.ok) {
        // 错误处理 - 与原型一致的文案
        if (data.detail?.code === 'USER_NOT_FOUND') {
          message.error('账号不存在')
        } else if (data.detail?.code === 'WRONG_PASSWORD') {
          message.error(data.detail.message || '密码错误')
        } else if (data.detail?.code === 'ACCOUNT_LOCKED') {
          message.error(data.detail.message || '账号已锁定')
        } else {
          message.error(data.detail?.message || '登录失败')
        }
        return
      }
      
      // 保存token
      localStorage.setItem('token', data.access_token)
      localStorage.setItem('user', JSON.stringify(data.user))
      
      message.success('登录成功')
      navigate('/')
    } catch (error) {
      message.error('网络错误，请稍后重试')
    } finally {
      setLoading(false)
    }
  }

  // 发送验证码
  const sendVerifyCode = async () => {
    if (!phone || phone.length !== 11) {
      message.error('请输入正确的手机号')
      return
    }
    
    try {
      // TODO: 调用发送验证码API
      message.success('验证码已发送')
      setCountdown(60)
      const timer = setInterval(() => {
        setCountdown(prev => {
          if (prev <= 1) {
            clearInterval(timer)
            return 0
          }
          return prev - 1
        })
      }, 1000)
    } catch (error) {
      message.error('发送失败，请稍后重试')
    }
  }

  // 登录表单
  const LoginForm = () => (
    <Form
      name="login"
      initialValues={{ remember: true }}
      onFinish={handleLogin}
      size="large"
    >
      <Form.Item
        name="username"
        rules={[{ required: true, message: '请输入用户名' }]}
      >
        <Input 
          prefix={<UserOutlined />} 
          placeholder="用户名/邮箱/手机号"
        />
      </Form.Item>

      <Form.Item
        name="password"
        rules={[{ required: true, message: '请输入密码' }]}
      >
        <Input.Password
          prefix={<LockOutlined />}
          placeholder="密码"
        />
      </Form.Item>

      <Form.Item>
        <div className="login-options">
          <Form.Item name="remember" valuePropName="checked" noStyle>
            <Checkbox>自动登录</Checkbox>
          </Form.Item>
          <Link onClick={() => setShowForgot(true)}>忘记密码</Link>
        </div>
      </Form.Item>

      <Form.Item>
        <Button type="primary" htmlType="submit" block loading={loading}>
          登录
        </Button>
      </Form.Item>
    </Form>
  )

  // 找回密码表单
  const ForgotPasswordForm = () => {
    const steps = [
      { title: '输入手机号' },
      { title: '验证' },
      { title: '设置密码' },
      { title: '完成' }
    ]

    return (
      <div className="forgot-password">
        <Steps current={forgotStep} items={steps} className="forgot-steps" />
        
        {forgotStep === ForgotStep.INPUT_PHONE && (
          <Form onFinish={() => setForgotStep(ForgotStep.VERIFY_CODE)}>
            <Form.Item
              name="phone"
              rules={[{ required: true, message: '请输入手机号' }, { len: 11, message: '手机号格式错误' }]}
            >
              <Input 
                prefix={<MobileOutlined />}
                placeholder="请输入手机号"
                maxLength={11}
                onChange={e => setPhone(e.target.value)}
              />
            </Form.Item>
            <Form.Item>
              <Button type="primary" htmlType="submit" block>
                下一步
              </Button>
            </Form.Item>
            <Button type="link" block onClick={() => setShowForgot(false)}>
              返回登录
            </Button>
          </Form>
        )}

        {forgotStep === ForgotStep.VERIFY_CODE && (
          <Form onFinish={() => setForgotStep(ForgotStep.SET_PASSWORD)}>
            <div className="verify-code-hint">
              验证码已发送至 {phone.replace(/(\d{3})\d{4}(\d{4})/, '$1****$2')}
            </div>
            <Form.Item
              name="code"
              rules={[{ required: true, message: '请输入验证码' }]}
            >
              <div className="verify-code-input">
                <Input 
                  prefix={<SafetyOutlined />}
                  placeholder="请输入验证码"
                  maxLength={6}
                />
                <Button 
                  disabled={countdown > 0}
                  onClick={sendVerifyCode}
                >
                  {countdown > 0 ? `${countdown}s后重发` : '获取验证码'}
                </Button>
              </div>
            </Form.Item>
            <Form.Item>
              <Button type="primary" htmlType="submit" block>
                下一步
              </Button>
            </Form.Item>
            <Button type="link" block onClick={() => setForgotStep(ForgotStep.INPUT_PHONE)}>
              上一步
            </Button>
          </Form>
        )}

        {forgotStep === ForgotStep.SET_PASSWORD && (
          <Form onFinish={() => setForgotStep(ForgotStep.SUCCESS)}>
            <Form.Item
              name="password"
              rules={[
                { required: true, message: '请输入新密码' },
                { min: 8, message: '密码至少8位' },
                { pattern: /^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)/, message: '需包含大小写字母和数字' }
              ]}
            >
              <Input.Password placeholder="新密码" />
            </Form.Item>
            <Form.Item
              name="confirmPassword"
              dependencies={['password']}
              rules={[
                { required: true, message: '请确认密码' },
                ({ getFieldValue }) => ({
                  validator(_, value) {
                    if (!value || getFieldValue('password') === value) {
                      return Promise.resolve()
                    }
                    return Promise.reject(new Error('两次输入的密码不一致'))
                  }
                })
              ]}
            >
              <Input.Password placeholder="确认密码" />
            </Form.Item>
            <div className="password-strength">
              <div className="strength-bar">
                <div className="strength-fill medium" />
              </div>
              <span className="strength-text">中</span>
            </div>
            <Form.Item>
              <Button type="primary" htmlType="submit" block>
                完成
              </Button>
            </Form.Item>
            <Button type="link" block onClick={() => setForgotStep(ForgotStep.VERIFY_CODE)}>
              上一步
            </Button>
          </Form>
        )}

        {forgotStep === ForgotStep.SUCCESS && (
          <div className="reset-success">
            <div className="success-icon">✓</div>
            <Title level={4}>密码重置成功</Title>
            <Text type="secondary">请使用新密码登录</Text>
            <Button 
              type="primary" 
              block 
              onClick={() => {
                setShowForgot(false)
                setForgotStep(ForgotStep.INPUT_PHONE)
              }}
            >
              立即登录
            </Button>
          </div>
        )}
      </div>
    )
  }

  return (
    <div className="login-page">
      <div className="login-container">
        <Card className="login-card">
          <div className="login-header">
            <div className="logo">
              <div className="logo-icon">AI</div>
              <div className="logo-text">
                <Title level={4}>AI快速BI报表工具</Title>
                <Text type="secondary">智能数据分析，从对话开始</Text>
              </div>
            </div>
          </div>
          
          {showForgot ? <ForgotPasswordForm /> : <LoginForm />}
        </Card>
        
        <div className="login-footer">
          <Text type="secondary">© 2026 AI-RiskViz Team</Text>
        </div>
      </div>
    </div>
  )
}