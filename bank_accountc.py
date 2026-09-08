class BankAccount:
    def __init__(self, account_number, holder_name, balance=0.0):
        self.account_number = account_number
        self.holder_name = holder_name
        self.balance = balance

    def deposit(self, amount):
        if amount > 0:
            self.balance += amount
            print(f"Deposited ₹{amount:.2f}. New balance: ₹{self.balance:.2f}")
        else:
            print("Deposit amount must be positive.")

    def withdraw(self, amount):
        if amount <= 0:
            print("Withdrawal amount must be positive.")
        elif amount > self.balance:
            print("Insufficient balance. Withdrawal denied.")
        else:
            self.balance -= amount
            print(f"Withdrawn ₹{amount:.2f}. New balance: ₹{self.balance:.2f}")

    def display_balance(self):
        print("\n----- Account Details -----")
        print(f"Account Number : {self.account_number}")
        print(f"Holder Name    : {self.holder_name}")
        print(f"Balance        : ₹{self.balance:.2f}")
        print("---------------------------")


# Demonstration
acc = BankAccount("1234567890", "Rahul Sharma", 5000.0)

acc.display_balance()

acc.deposit(1500)
acc.withdraw(2000)
acc.withdraw(6000)          # Should be rejected (insufficient balance)
acc.deposit(-100)           # Invalid deposit
acc.withdraw(-50)           # Invalid withdrawal

acc.display_balance()