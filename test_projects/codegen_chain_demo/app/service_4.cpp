#include "service_4.h"

Service4::Service4() {}

void Service4::execute() {
    for (auto& cb : callbacks_) cb();
}

void Service4::registerCallback(std::function<void()> cb) {
    callbacks_.push_back(cb);
}
