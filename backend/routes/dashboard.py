from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from datetime import datetime, timedelta
import sys
import os
import random
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from models import db, Battery, BMSRecord, ChargingRecord, RecyclingRecord, ScrapAssessment, CarbonFootprint

dashboard_bp = Blueprint('dashboard', __name__)

@dashboard_bp.route('/overview', methods=['GET'])
@jwt_required()
def overview():
    automaker = request.args.get('automaker', '')
    
    battery_query = Battery.query
    if automaker:
        battery_query = battery_query.filter(Battery.automaker == automaker)
    
    bms_query = BMSRecord.query
    if automaker:
        ids = [b.id for b in Battery.query.filter_by(automaker=automaker).all()]
        bms_query = bms_query.filter(BMSRecord.battery_id.in_(ids))
    
    charging_query = ChargingRecord.query
    if automaker:
        ids = [b.id for b in Battery.query.filter_by(automaker=automaker).all()]
        charging_query = charging_query.filter(ChargingRecord.battery_id.in_(ids))
    
    recycling_query = RecyclingRecord.query
    if automaker:
        ids = [b.id for b in Battery.query.filter_by(automaker=automaker).all()]
        recycling_query = recycling_query.filter(RecyclingRecord.battery_id.in_(ids))
    
    total_batteries = battery_query.count()
    in_use = battery_query.filter(Battery.status == 'in_use').count()
    installed = battery_query.filter(Battery.status == 'installed').count()
    scrapped = battery_query.filter(Battery.status.in_(['scrapped', 'second_life'])).count()
    recycled = battery_query.filter(Battery.status == 'recycled').count()
    produced = battery_query.filter(Battery.status == 'produced').count()
    online_rate = round((in_use + installed) / total_batteries * 100, 1) if total_batteries > 0 else 0
    
    second_life_count = battery_query.filter(Battery.status == 'second_life').count()
    total_scrapped = battery_query.filter(Battery.status.in_(['scrapped', 'second_life', 'recycled'])).count()
    cascading_rate = round(second_life_count / total_scrapped * 100, 1) if total_scrapped > 0 else 0
    
    warning_count = bms_query.filter(BMSRecord.is_abnormal == True).count()
    critical_count = bms_query.filter(BMSRecord.warning_type.contains('紧急')).count()
    
    total_metals = recycling_query.with_entities(
        db.func.sum(RecyclingRecord.lithium_extracted),
        db.func.sum(RecyclingRecord.cobalt_extracted),
        db.func.sum(RecyclingRecord.nickel_extracted),
        db.func.sum(RecyclingRecord.manganese_extracted),
        db.func.sum(RecyclingRecord.other_metals)
    ).first()
    
    total_carbon = CarbonFootprint.query.with_entities(db.func.sum(CarbonFootprint.total_carbon)).scalar() or 0
    total_saved = CarbonFootprint.query.with_entities(db.func.sum(CarbonFootprint.carbon_saved)).scalar() or 0
    
    return jsonify({
        'code': 200,
        'data': {
            'total_batteries': total_batteries,
            'in_use': in_use,
            'installed': installed,
            'scrapped': scrapped,
            'recycled': recycled,
            'produced': produced,
            'online_rate': online_rate,
            'cascading_rate': cascading_rate,
            'warning_count': warning_count,
            'critical_count': critical_count,
            'total_vehicles_with_battery': in_use + installed,
            'recycled_metals': {
                'lithium': round(total_metals[0] or 0, 2),
                'cobalt': round(total_metals[1] or 0, 2),
                'nickel': round(total_metals[2] or 0, 2),
                'manganese': round(total_metals[3] or 0, 2),
                'other': round(total_metals[4] or 0, 2),
                'total': round((total_metals[0] or 0) + (total_metals[1] or 0) + (total_metals[2] or 0) + (total_metals[3] or 0) + (total_metals[4] or 0), 2)
            },
            'carbon': {
                'total_emission': round(total_carbon, 2),
                'total_saved': round(total_saved, 2),
                'net_emission': round(max(0, total_carbon - total_saved), 2)
            }
        }
    })

@dashboard_bp.route('/status-chart', methods=['GET'])
@jwt_required()
def status_chart():
    automaker = request.args.get('automaker', '')
    query = Battery.query
    if automaker:
        query = query.filter(Battery.automaker == automaker)
    
    statuses = ['produced', 'installed', 'in_use', 'scrapped', 'second_life', 'recycled']
    labels = ['已生产', '已装车', '使用中', '已报废', '梯次利用', '已回收拆解']
    data = [query.filter(Battery.status == s).count() for s in statuses]
    
    return jsonify({
        'code': 200,
        'data': {'labels': labels, 'values': data}
    })

@dashboard_bp.route('/factory-chart', methods=['GET'])
@jwt_required()
def factory_chart():
    results = db.session.query(
        Battery.battery_factory, db.func.count(Battery.id)
    ).filter(Battery.battery_factory.isnot(None)).group_by(Battery.battery_factory).all()
    
    return jsonify({
        'code': 200,
        'data': [{'factory': r[0], 'count': r[1]} for r in results]
    })

@dashboard_bp.route('/automaker-chart', methods=['GET'])
@jwt_required()
def automaker_chart():
    results = db.session.query(
        Battery.automaker, db.func.count(Battery.id)
    ).filter(Battery.automaker.isnot(None)).group_by(Battery.automaker).all()
    
    return jsonify({
        'code': 200,
        'data': [{'automaker': r[0], 'count': r[1]} for r in results]
    })

@dashboard_bp.route('/soh-distribution', methods=['GET'])
@jwt_required()
def soh_distribution():
    ranges = [(90, 100, '优秀 (≥90%)'), (80, 90, '良好 (80-90%)'), (70, 80, '正常 (70-80%)'), (60, 70, '衰减 (60-70%)'), (0, 60, '需更换 (<60%)')]
    data = []
    for min_r, max_r, label in ranges:
        c = Battery.query.filter(Battery.current_soh >= min_r, Battery.current_soh < max_r).count()
        data.append({'label': label, 'value': c, 'min': min_r, 'max': max_r})
    return jsonify({'code': 200, 'data': data})

@dashboard_bp.route('/trend', methods=['GET'])
@jwt_required()
def trend():
    days = int(request.args.get('days', 7))
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    labels = []
    new_data = []
    recycled_data = []
    warning_data = []
    
    for i in range(days - 1, -1, -1):
        day = today - timedelta(days=i)
        next_day = day + timedelta(days=1)
        labels.append(day.strftime('%m-%d'))
        
        new_data.append(Battery.query.filter(Battery.created_at >= day, Battery.created_at < next_day).count())
        recycled_data.append(RecyclingRecord.query.filter(RecyclingRecord.created_at >= day, RecyclingRecord.created_at < next_day).count())
        warning_data.append(BMSRecord.query.filter(BMSRecord.is_abnormal == True, BMSRecord.record_time >= day, BMSRecord.record_time < next_day).count())
    
    return jsonify({
        'code': 200,
        'data': {
            'labels': labels,
            'new_batteries': new_data,
            'recycled': recycled_data,
            'warnings': warning_data
        }
    })

@dashboard_bp.route('/warnings-realtime', methods=['GET'])
@jwt_required()
def warnings_realtime():
    automaker = request.args.get('automaker', '')
    query = BMSRecord.query.filter(BMSRecord.is_abnormal == True)
    
    if automaker:
        ids = [b.id for b in Battery.query.filter_by(automaker=automaker).all()]
        query = query.filter(BMSRecord.battery_id.in_(ids))
    
    records = query.order_by(BMSRecord.record_time.desc()).limit(10).all()
    return jsonify({
        'code': 200,
        'data': [r.to_dict() for r in records]
    })

@dashboard_bp.route('/automakers', methods=['GET'])
@jwt_required()
def automakers():
    results = db.session.query(Battery.automaker).filter(Battery.automaker.isnot(None)).distinct().all()
    return jsonify({'code': 200, 'data': [r[0] for r in results if r[0]]})
