from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
import random

db = SQLAlchemy()

ROLES = {
    'battery_factory': '电池厂',
    'automaker': '车企',
    'recycler': '回收商',
    'regulator': '监管部门'
}

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(50), nullable=False)
    company_name = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.now)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'role': self.role,
            'role_name': ROLES.get(self.role, self.role),
            'company_name': self.company_name,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S')
        }

class Battery(db.Model):
    __tablename__ = 'batteries'
    id = db.Column(db.Integer, primary_key=True)
    serial_code = db.Column(db.String(64), unique=True, nullable=False)
    cell_model = db.Column(db.String(100), nullable=False)
    capacity = db.Column(db.Float, nullable=False)
    production_batch = db.Column(db.String(100), nullable=False)
    production_date = db.Column(db.DateTime, nullable=False)
    battery_factory = db.Column(db.String(200))
    automaker = db.Column(db.String(200))
    vehicle_plate = db.Column(db.String(50))
    status = db.Column(db.String(50), default='produced')
    status_name = db.Column(db.String(50), default='已生产')
    current_soh = db.Column(db.Float, default=100.0)
    remaining_capacity = db.Column(db.Float, default=0)
    created_at = db.Column(db.DateTime, default=datetime.now)
    bms_records = db.relationship('BMSRecord', backref='battery', lazy=True)
    charging_records = db.relationship('ChargingRecord', backref='battery', lazy=True)

    def to_dict(self):
        return {
            'id': self.id,
            'serial_code': self.serial_code,
            'cell_model': self.cell_model,
            'capacity': self.capacity,
            'production_batch': self.production_batch,
            'production_date': self.production_date.strftime('%Y-%m-%d') if self.production_date else None,
            'battery_factory': self.battery_factory,
            'automaker': self.automaker,
            'vehicle_plate': self.vehicle_plate,
            'status': self.status,
            'status_name': self.status_name,
            'current_soh': self.current_soh,
            'remaining_capacity': self.remaining_capacity,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S')
        }

STATUS_MAP = {
    'produced': '已生产',
    'shipped': '已发货',
    'installed': '已装车',
    'in_use': '使用中',
    'scrapped': '已报废',
    'second_life': '梯次利用',
    'recycled': '已回收拆解'
}

class BMSRecord(db.Model):
    __tablename__ = 'bms_records'
    id = db.Column(db.Integer, primary_key=True)
    battery_id = db.Column(db.Integer, db.ForeignKey('batteries.id'), nullable=False)
    voltage = db.Column(db.Float, nullable=False)
    current = db.Column(db.Float, default=0)
    temperature = db.Column(db.Float, nullable=False)
    soc = db.Column(db.Float, nullable=False)
    soh = db.Column(db.Float, nullable=False)
    cell_temperatures = db.Column(db.String(500))
    cell_voltages = db.Column(db.String(500))
    is_abnormal = db.Column(db.Boolean, default=False)
    warning_type = db.Column(db.String(200))
    record_time = db.Column(db.DateTime, default=datetime.now)

    def to_dict(self):
        return {
            'id': self.id,
            'battery_id': self.battery_id,
            'serial_code': self.battery.serial_code if self.battery else '',
            'voltage': self.voltage,
            'current': self.current,
            'temperature': self.temperature,
            'soc': self.soc,
            'soh': self.soh,
            'cell_temperatures': self.cell_temperatures,
            'cell_voltages': self.cell_voltages,
            'is_abnormal': self.is_abnormal,
            'warning_type': self.warning_type,
            'record_time': self.record_time.strftime('%Y-%m-%d %H:%M:%S')
        }

class ChargingRecord(db.Model):
    __tablename__ = 'charging_records'
    id = db.Column(db.Integer, primary_key=True)
    battery_id = db.Column(db.Integer, db.ForeignKey('batteries.id'), nullable=False)
    start_soc = db.Column(db.Float, nullable=False)
    end_soc = db.Column(db.Float)
    charging_strategy = db.Column(db.String(200))
    charging_power = db.Column(db.Float)
    max_temperature = db.Column(db.Float)
    is_alerted = db.Column(db.Boolean, default=False)
    alert_message = db.Column(db.String(500))
    start_time = db.Column(db.DateTime, default=datetime.now)
    end_time = db.Column(db.DateTime)
    status = db.Column(db.String(50), default='charging')

    def to_dict(self):
        return {
            'id': self.id,
            'battery_id': self.battery_id,
            'serial_code': self.battery.serial_code if self.battery else '',
            'vehicle_plate': self.battery.vehicle_plate if self.battery else '',
            'start_soc': self.start_soc,
            'end_soc': self.end_soc,
            'charging_strategy': self.charging_strategy,
            'charging_power': self.charging_power,
            'max_temperature': self.max_temperature,
            'is_alerted': self.is_alerted,
            'alert_message': self.alert_message,
            'start_time': self.start_time.strftime('%Y-%m-%d %H:%M:%S') if self.start_time else None,
            'end_time': self.end_time.strftime('%Y-%m-%d %H:%M:%S') if self.end_time else None,
            'status': self.status
        }

class ScrapAssessment(db.Model):
    __tablename__ = 'scrap_assessments'
    id = db.Column(db.Integer, primary_key=True)
    battery_id = db.Column(db.Integer, db.ForeignKey('batteries.id'), nullable=False)
    battery = db.relationship('Battery', backref='scrap_assessments')
    final_soh = db.Column(db.Float, nullable=False)
    residual_value = db.Column(db.Float)
    recommended_scenario = db.Column(db.String(200))
    scenario_detail = db.Column(db.String(1000))
    created_at = db.Column(db.DateTime, default=datetime.now)

    def to_dict(self):
        return {
            'id': self.id,
            'battery_id': self.battery_id,
            'serial_code': self.battery.serial_code if self.battery else '',
            'final_soh': self.final_soh,
            'residual_value': self.residual_value,
            'recommended_scenario': self.recommended_scenario,
            'scenario_detail': self.scenario_detail,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S')
        }

class RecyclingRecord(db.Model):
    __tablename__ = 'recycling_records'
    id = db.Column(db.Integer, primary_key=True)
    battery_id = db.Column(db.Integer, db.ForeignKey('batteries.id'), nullable=False)
    battery = db.relationship('Battery', backref='recycling_records')
    recycler_name = db.Column(db.String(200))
    inbound_code = db.Column(db.String(100))
    disassembly_order = db.Column(db.String(100))
    lithium_extracted = db.Column(db.Float, default=0)
    cobalt_extracted = db.Column(db.Float, default=0)
    nickel_extracted = db.Column(db.Float, default=0)
    manganese_extracted = db.Column(db.Float, default=0)
    other_metals = db.Column(db.Float, default=0)
    disassembly_status = db.Column(db.String(50), default='pending')
    created_at = db.Column(db.DateTime, default=datetime.now)
    completed_at = db.Column(db.DateTime)

    def to_dict(self):
        return {
            'id': self.id,
            'battery_id': self.battery_id,
            'serial_code': self.battery.serial_code if self.battery else '',
            'recycler_name': self.recycler_name,
            'inbound_code': self.inbound_code,
            'disassembly_order': self.disassembly_order,
            'lithium_extracted': self.lithium_extracted,
            'cobalt_extracted': self.cobalt_extracted,
            'nickel_extracted': self.nickel_extracted,
            'manganese_extracted': self.manganese_extracted,
            'other_metals': self.other_metals,
            'disassembly_status': self.disassembly_status,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            'completed_at': self.completed_at.strftime('%Y-%m-%d %H:%M:%S') if self.completed_at else None
        }

class CarbonFootprint(db.Model):
    __tablename__ = 'carbon_footprints'
    id = db.Column(db.Integer, primary_key=True)
    battery_id = db.Column(db.Integer, db.ForeignKey('batteries.id'), nullable=False)
    battery = db.relationship('Battery', backref='carbon_footprints')
    production_carbon = db.Column(db.Float, default=0)
    transport_carbon = db.Column(db.Float, default=0)
    usage_carbon = db.Column(db.Float, default=0)
    recycling_carbon = db.Column(db.Float, default=0)
    total_carbon = db.Column(db.Float, default=0)
    carbon_saved = db.Column(db.Float, default=0)
    compliance_report = db.Column(db.Text)
    calculated_at = db.Column(db.DateTime, default=datetime.now)

    def to_dict(self):
        return {
            'id': self.id,
            'battery_id': self.battery_id,
            'serial_code': self.battery.serial_code if self.battery else '',
            'production_carbon': self.production_carbon,
            'transport_carbon': self.transport_carbon,
            'usage_carbon': self.usage_carbon,
            'recycling_carbon': self.recycling_carbon,
            'total_carbon': self.total_carbon,
            'carbon_saved': self.carbon_saved,
            'compliance_report': self.compliance_report,
            'calculated_at': self.calculated_at.strftime('%Y-%m-%d %H:%M:%S')
        }

def init_db():
    db.create_all()
    
    if User.query.count() == 0:
        users_data = [
            {'username': 'admin', 'password': '123456', 'role': 'regulator', 'company_name': '国家新能源监管中心'},
            {'username': 'battery1', 'password': '123456', 'role': 'battery_factory', 'company_name': '宁德时代新能源科技'},
            {'username': 'auto1', 'password': '123456', 'role': 'automaker', 'company_name': '比亚迪汽车'},
            {'username': 'recycle1', 'password': '123456', 'role': 'recycler', 'company_name': '格林美回收科技'}
        ]
        for u in users_data:
            user = User(username=u['username'], role=u['role'], company_name=u['company_name'])
            user.set_password(u['password'])
            db.session.add(user)
    
    if Battery.query.count() == 0:
        automakers = ['比亚迪汽车', '特斯拉中国', '蔚来汽车', '小鹏汽车', '理想汽车']
        factories = ['宁德时代新能源科技', '比亚迪电池事业部', '国轩高科', '中创新航', '亿纬锂能']
        cell_models = ['NCM811', 'NCM622', 'LFP-280', 'LFP-302', 'NCM955']
        
        for i in range(50):
            year = 2023 + random.randint(0, 1)
            month = random.randint(1, 12)
            day = random.randint(1, 28)
            statuses = ['produced', 'installed', 'in_use', 'in_use', 'in_use', 'scrapped', 'second_life', 'recycled']
            status = statuses[random.randint(0, min(i//5, 7))]
            soh = 100.0
            if status in ['in_use']:
                soh = round(random.uniform(75, 98), 1)
            elif status in ['scrapped', 'second_life']:
                soh = round(random.uniform(40, 70), 1)
            elif status == 'recycled':
                soh = round(random.uniform(20, 40), 1)
            
            b = Battery(
                serial_code=f'BT{year:04d}{i+1:06d}',
                cell_model=cell_models[random.randint(0, 4)],
                capacity=random.choice([50, 65, 75, 85, 100, 120]),
                production_batch=f'BATCH{year}-{random.randint(1, 999):03d}',
                production_date=datetime(year, month, day),
                battery_factory=factories[random.randint(0, 4)],
                automaker=automakers[random.randint(0, 4)] if status != 'produced' else None,
                vehicle_plate=f'京A{random.randint(10000, 99999)}' if status in ['installed', 'in_use', 'scrapped'] else None,
                status=status,
                status_name=STATUS_MAP[status],
                current_soh=soh,
                remaining_capacity=round(soh * random.choice([50, 65, 75, 85, 100, 120]) / 100, 2)
            )
            db.session.add(b)
    
    db.session.commit()
    
    if BMSRecord.query.count() == 0:
        batteries = Battery.query.filter(Battery.status.in_(['installed', 'in_use'])).all()
        for bat in batteries:
            for j in range(random.randint(20, 100)):
                temp = round(random.uniform(22, 42), 1)
                abnormal = temp > 40 or temp < 0
                warning = None
                if temp > 45:
                    warning = '过温告警-紧急断电'
                elif temp > 40:
                    warning = '过温预警'
                
                bms = BMSRecord(
                    battery_id=bat.id,
                    voltage=round(random.uniform(320, 410), 2),
                    current=round(random.uniform(-150, 200), 2),
                    temperature=temp,
                    soc=round(random.uniform(10, 100), 1),
                    soh=bat.current_soh + round(random.uniform(-2, 1), 2),
                    cell_temperatures=','.join([str(round(random.uniform(22, 42), 1)) for _ in range(96)]),
                    cell_voltages=','.join([str(round(random.uniform(3.2, 4.2), 3)) for _ in range(96)]),
                    is_abnormal=abnormal,
                    warning_type=warning,
                    record_time=datetime.now() - timedelta(hours=random.randint(1, 24*30))
                )
                db.session.add(bms)
    
    db.session.commit()
    
    if ChargingRecord.query.count() == 0:
        batteries = Battery.query.filter(Battery.status.in_(['installed', 'in_use', 'scrapped'])).all()
        for bat in batteries:
            for j in range(random.randint(5, 30)):
                start_soc = round(random.uniform(10, 40), 1)
                end_soc = round(start_soc + random.uniform(30, 80), 1)
                end_soc = min(end_soc, 100)
                max_temp = round(random.uniform(28, 46), 1)
                alerted = max_temp > 42
                
                cr = ChargingRecord(
                    battery_id=bat.id,
                    start_soc=start_soc,
                    end_soc=end_soc,
                    charging_strategy=random.choice(['标准恒流充电', '快速补能策略', '低温预热策略', '高温保护策略', 'SOH优化策略']),
                    charging_power=round(random.uniform(20, 250), 1),
                    max_temperature=max_temp,
                    is_alerted=alerted,
                    alert_message='电池温度过高，已自动降低充电功率并启动散热' if alerted else None,
                    start_time=datetime.now() - timedelta(days=random.randint(1, 90), hours=random.randint(0, 23)),
                    end_time=datetime.now() - timedelta(days=random.randint(0, 89), hours=random.randint(0, 23)),
                    status='completed'
                )
                db.session.add(cr)
    
    db.session.commit()
    
    if ScrapAssessment.query.count() == 0:
        batteries = Battery.query.filter(Battery.status.in_(['scrapped', 'second_life'])).all()
        for bat in batteries:
            soh = bat.current_soh
            if soh >= 60:
                scenario = '储能电站 - 削峰填谷'
                detail = '电池SOH较高，适合用于电网级储能系统，预计可服役5-8年'
                value = round(soh * 80, 0)
            elif soh >= 40:
                scenario = '低速电动车 / 电动叉车'
                detail = '电池SOH中等，适合用于低速车辆及工程机械'
                value = round(soh * 50, 0)
            else:
                scenario = '拆解回收 - 提取贵金属'
                detail = '电池SOH较低，建议拆解回收锂、钴、镍等贵金属'
                value = round(soh * 25, 0)
            
            sa = ScrapAssessment(
                battery_id=bat.id,
                final_soh=soh,
                residual_value=value,
                recommended_scenario=scenario,
                scenario_detail=detail
            )
            db.session.add(sa)
    
    db.session.commit()
    
    if RecyclingRecord.query.count() == 0:
        batteries = Battery.query.filter(Battery.status == 'recycled').all()
        for idx, bat in enumerate(batteries):
            rr = RecyclingRecord(
                battery_id=bat.id,
                recycler_name='格林美回收科技' if idx % 2 == 0 else '天奇自动化回收',
                inbound_code=f'IN{datetime.now().year}{idx+1:05d}',
                disassembly_order=f'DO{datetime.now().year}{idx+1:05d}',
                lithium_extracted=round(random.uniform(2.5, 6.5), 3),
                cobalt_extracted=round(random.uniform(0.5, 3.5), 3),
                nickel_extracted=round(random.uniform(1.5, 8.5), 3),
                manganese_extracted=round(random.uniform(0.3, 2.0), 3),
                other_metals=round(random.uniform(0.5, 5.0), 3),
                disassembly_status='completed',
                created_at=datetime.now() - timedelta(days=random.randint(10, 60)),
                completed_at=datetime.now() - timedelta(days=random.randint(1, 10))
            )
            db.session.add(rr)
    
    db.session.commit()
    
    if CarbonFootprint.query.count() == 0:
        batteries = Battery.query.all()
        for bat in batteries:
            cap = bat.capacity
            prod_carbon = round(cap * 12.5, 2)
            trans_carbon = round(random.uniform(15, 85), 2)
            usage_carbon = round(cap * random.uniform(8, 18), 2) if bat.status in ['in_use', 'scrapped', 'second_life', 'recycled'] else 0
            rec_carbon = round(random.uniform(20, 120), 2) if bat.status == 'recycled' else 0
            total = round(prod_carbon + trans_carbon + usage_carbon + rec_carbon, 2)
            saved = round(rec_carbon * 0.65 + (cap * 10 if bat.status in ['second_life'] else 0), 2)
            
            cf = CarbonFootprint(
                battery_id=bat.id,
                production_carbon=prod_carbon,
                transport_carbon=trans_carbon,
                usage_carbon=usage_carbon,
                recycling_carbon=rec_carbon,
                total_carbon=total,
                carbon_saved=saved,
                compliance_report=f'电池{bat.serial_code}全生命周期碳排放核算报告\n\n'
                                 f'一、电池基本信息\n'
                                 f'  编码: {bat.serial_code}\n'
                                 f'  型号: {bat.cell_model}\n'
                                 f'  容量: {bat.capacity}kWh\n'
                                 f'  生产批次: {bat.production_batch}\n\n'
                                 f'二、碳排放明细 (单位: kgCO2e)\n'
                                 f'  生产阶段: {prod_carbon:.2f}\n'
                                 f'  运输阶段: {trans_carbon:.2f}\n'
                                 f'  使用阶段: {usage_carbon:.2f}\n'
                                 f'  回收阶段: {rec_carbon:.2f}\n'
                                 f'  总计: {total:.2f}\n\n'
                                 f'三、碳减排量: {saved:.2f} kgCO2e\n\n'
                                 f'四、合规性说明\n'
                                 f'  本核算遵循ISO 14067标准，符合工信部《新能源汽车动力蓄电池回收利用管理办法》要求。\n'
                                 f'  核算日期: {datetime.now().strftime("%Y-%m-%d")}'
            )
            db.session.add(cf)
    
    db.session.commit()
    print('数据库初始化完成！')
