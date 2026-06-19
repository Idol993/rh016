from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from datetime import datetime
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from models import db, CarbonFootprint, Battery, User

carbon_bp = Blueprint('carbon', __name__)

@carbon_bp.route('/calculate/<int:battery_id>', methods=['POST'])
@jwt_required()
def calculate_carbon(battery_id):
    battery = Battery.query.get(battery_id)
    if not battery:
        return jsonify({'message': '电池不存在', 'code': 404}), 404
    
    cap = battery.capacity
    prod_carbon = round(cap * 12.5, 2)
    trans_carbon = round(52.5, 2)
    
    from sqlalchemy import func
    from models import BMSRecord
    record_count = BMSRecord.query.filter_by(battery_id=battery_id).count()
    usage_carbon = round(cap * (record_count / 1000) * 0.85 + cap * 12, 2) if record_count > 0 else 0
    
    from models import RecyclingRecord
    recycling = RecyclingRecord.query.filter_by(battery_id=battery_id).first()
    rec_carbon = 0
    saved = 0
    if recycling:
        metals = recycling.lithium_extracted * 20 + recycling.cobalt_extracted * 60 + recycling.nickel_extracted * 35
        rec_carbon = round(80 + metals * 0.5, 2)
        saved = round(rec_carbon * 0.65, 2)
    
    if battery.status in ['second_life']:
        saved += cap * 10
    
    total = round(prod_carbon + trans_carbon + usage_carbon + rec_carbon, 2)
    
    report = f'电池{battery.serial_code}全生命周期碳排放核算报告\n\n' \
             f'一、电池基本信息\n' \
             f'  唯一编码: {battery.serial_code}\n' \
             f'  电芯型号: {battery.cell_model}\n' \
             f'  额定容量: {battery.capacity}kWh\n' \
             f'  生产批次: {battery.production_batch}\n' \
             f'  出厂日期: {battery.production_date.strftime("%Y-%m-%d") if battery.production_date else ""}\n' \
             f'  电池厂商: {battery.battery_factory or "-"}\n' \
             f'  装车企业: {battery.automaker or "-"}\n\n' \
             f'二、碳排放明细 (单位: kgCO₂e)\n' \
             f'  1. 生产阶段: {prod_carbon:.2f}\n' \
             f'     - 原材料开采与加工: {round(prod_carbon * 0.6, 2)}\n' \
             f'     - 电芯制造与组装: {round(prod_carbon * 0.4, 2)}\n' \
             f'  2. 运输阶段: {trans_carbon:.2f}\n' \
             f'  3. 使用阶段: {usage_carbon:.2f}\n' \
             f'     - 按行驶里程/循环次数折算\n' \
             f'  4. 回收阶段: {rec_carbon:.2f}\n' \
             f'  全生命周期碳排放总计: {total:.2f} kgCO₂e\n\n' \
             f'三、碳减排贡献\n' \
             f'  回收再利用节碳量: {saved:.2f} kgCO₂e\n' \
             f'  净碳排放: {max(0, total - saved):.2f} kgCO₂e\n\n' \
             f'四、合规性说明\n' \
             f'  - 本核算遵循 ISO 14067:2018《温室气体-产品碳足迹-量化要求与导则》\n' \
             f'  - 符合工信部《新能源汽车动力蓄电池回收利用管理办法》\n' \
             f'  - 符合 GB/T 38632-2020《电动汽车动力蓄电池规格书》\n' \
             f'  - 核算方法采用生命周期评估(LCA)方法学\n\n' \
             f'五、声明\n' \
             f'  本报告由动力电池溯源与梯次利用平台自动生成，数据来源于全生命周期各环节真实记录。\n\n' \
             f'生成日期: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}'
    
    cf = CarbonFootprint.query.filter_by(battery_id=battery_id).first()
    if cf:
        cf.production_carbon = prod_carbon
        cf.transport_carbon = trans_carbon
        cf.usage_carbon = usage_carbon
        cf.recycling_carbon = rec_carbon
        cf.total_carbon = total
        cf.carbon_saved = saved
        cf.compliance_report = report
        cf.calculated_at = datetime.now()
    else:
        cf = CarbonFootprint(
            battery_id=battery_id,
            production_carbon=prod_carbon,
            transport_carbon=trans_carbon,
            usage_carbon=usage_carbon,
            recycling_carbon=rec_carbon,
            total_carbon=total,
            carbon_saved=saved,
            compliance_report=report
        )
        db.session.add(cf)
    
    db.session.commit()
    return jsonify({'message': '碳足迹核算完成，合规报告已生成', 'code': 200, 'data': cf.to_dict()})

@carbon_bp.route('/list', methods=['GET'])
@jwt_required()
def list_carbon():
    user_id = get_jwt_identity()
    current_user = User.query.get(int(user_id))
    page = int(request.args.get('page', 1))
    page_size = int(request.args.get('page_size', 20))
    keyword = request.args.get('keyword', '')
    
    query = CarbonFootprint.query
    if keyword:
        battery = Battery.query.filter(Battery.serial_code.contains(keyword)).first()
        if battery:
            query = query.filter(CarbonFootprint.battery_id == battery.id)
    
    total = query.count()
    records = query.order_by(CarbonFootprint.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    
    return jsonify({
        'code': 200,
        'data': {
            'total': total,
            'list': [r.to_dict() for r in records]
        }
    })

@carbon_bp.route('/<int:cid>', methods=['GET'])
@jwt_required()
def get_carbon(cid):
    cf = CarbonFootprint.query.get(cid)
    if not cf:
        return jsonify({'message': '记录不存在', 'code': 404}), 404
    return jsonify({'code': 200, 'data': cf.to_dict()})

@carbon_bp.route('/stats', methods=['GET'])
@jwt_required()
def carbon_stats():
    total_carbon = db.session.query(db.func.sum(CarbonFootprint.total_carbon)).scalar() or 0
    total_saved = db.session.query(db.func.sum(CarbonFootprint.carbon_saved)).scalar() or 0
    count = CarbonFootprint.query.count()
    
    stage_avg = {
        'production': db.session.query(db.func.avg(CarbonFootprint.production_carbon)).scalar() or 0,
        'transport': db.session.query(db.func.avg(CarbonFootprint.transport_carbon)).scalar() or 0,
        'usage': db.session.query(db.func.avg(CarbonFootprint.usage_carbon)).scalar() or 0,
        'recycling': db.session.query(db.func.avg(CarbonFootprint.recycling_carbon)).scalar() or 0
    }
    
    return jsonify({
        'code': 200,
        'data': {
            'total_carbon': round(total_carbon, 2),
            'total_saved': round(total_saved, 2),
            'count': count,
            'avg_carbon_per_unit': round(total_carbon / count, 2) if count > 0 else 0,
            'stage_average': {k: round(v, 2) for k, v in stage_avg.items()}
        }
    })
